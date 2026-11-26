/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    /**
     * @override
     *
     * Show on a voucher method's button what it can still pay.
     */
    getPaymentMethodFmtAmount(pm, order) {
        if (pm.isMollieVoucher) {
            return `(${this.formatCurrency(order.getMollieVoucherRemaining(pm))})`;
        }
        return super.getPaymentMethodFmtAmount(...arguments);
    },

    /**
     * @override
     *
     * `pos_mollie` drops a paid notification no line follows (e.g. its line was removed): sync the
     * current order then. Not through `PaymentInterface.connectWebSocket`: it keeps one handler per
     * channel, `pos_mollie`'s.
     */
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.data.connectWebSocket("MOLLIE_PAYMENT_STATUS", (payload) => {
            const order = this.getOrder();
            const isFollowed = this.models["pos.payment"].find(
                (paymentLine) => paymentLine.transaction_id === payload.payment_id
            );
            if (payload.status === "paid" && payload.session_id === this.session.id && order && !isFollowed) {
                this.syncMollieOrder(order).catch(() => {});
            }
        });
        return result;
    },

    /**
     * Make the order's payment lines match its Mollie payments (see `mollie_get_order_payments`):
     * each paid payment gets one done line at the paid amount (the line following it, else the
     * line that made it, else a new line), so no paid payment is lost. A Retry line whose own
     * payment is still open waits for it. A failure only moves the line waiting for that payment
     * to Retry. Lines being sent (`waiting`) are left to their request. When a paid line is added
     * back, the unsent Mollie lines are removed: their amount no longer holds. Running it again
     * changes nothing.
     *
     * @param {Object} order
     * @returns {Promise<boolean>} whether a paid payment was recorded or a Retry line now waits for
     *     its own payment: the send must stop
     */
    async syncMollieOrder(order) {
        const molliePaymentMethod = this.config.payment_method_ids.find((pm) => pm.payment_provider === "mollie");
        if (!molliePaymentMethod || order.finalized) {
            return false;
        }
        const molliePayments = await molliePaymentMethod.payment_interface.callPaymentMethod(
            "mollie_get_order_payments",
            [molliePaymentMethod.id, order.uuid]
        );
        if (order.finalized) {
            return false;
        }
        let changed = false;
        let addedBack = false;
        for (const molliePayment of molliePayments) {
            const paymentMethod = this.config.payment_method_ids.find(
                (pm) => pm.id === molliePayment.payment_method_id
            );
            if (!paymentMethod) {
                continue;
            }

            // The line following this payment (by transaction id).
            let existingPaymentLine = order.payment_ids.find(
                (paymentLine) => paymentLine.transaction_id === molliePayment.id
            );
            // Already recorded.
            if (existingPaymentLine?.isDone()) {
                continue;
            }
            // If no line follows it, the line that made it (by uuid), unless that line is done.
            if (!existingPaymentLine) {
                existingPaymentLine = order.payment_ids.find(
                    (paymentLine) => paymentLine.uuid === molliePayment.payment_uuid && !paymentLine.isDone()
                );
            }

            // Its create request is still waiting for Mollie's answer, which sets its status: leave it,
            // the next sync handles it.
            if (existingPaymentLine?.payment_status === "waiting") {
                continue;
            }

            const paymentInterface = paymentMethod.payment_interface;
            const statusMessage = paymentInterface._mollieStatusMessage(molliePayment);

            if (molliePayment.status === "paid") {
                // Its line was removed: add it back. Not addPaymentline: it refuses while another
                // line of the method is in progress.
                if (!existingPaymentLine) {
                    const amount = parseFloat(molliePayment.amount.value);
                    existingPaymentLine = this.models["pos.payment"].create({
                        pos_order_id: order,
                        payment_method_id: paymentMethod,
                        amount,
                    });
                    addedBack = true;
                    this.notification.add(
                        _t(
                            "A terminal payment of %s was already paid and is added to the order. Check what is still due.",
                            this.formatCurrency(amount)
                        ),
                        { type: "warning" }
                    );
                }
                paymentInterface._followMolliePayment(existingPaymentLine, molliePayment);
                paymentInterface.handleMollieStatusResponse(existingPaymentLine, statusMessage);
                changed = true;
            } else if (["open", "pending"].includes(molliePayment.status)) {
                // A Retry line waits for its own open payment instead of sending a new one (e.g. the
                // POS lost the answer to its request).
                if (existingPaymentLine?.payment_status === "retry") {
                    paymentInterface._followMolliePayment(existingPaymentLine, molliePayment);
                    paymentInterface
                        ._waitForPaymentConfirmation(existingPaymentLine)
                        .then((paid) => existingPaymentLine.handlePaymentResponse(paid));
                    changed = true;
                }
            } else if (["failed", "canceled", "expired"].includes(molliePayment.status)) {
                // Only the line waiting for this payment goes to Retry: an older attempt's failure
                // never moves a line back. Not a change for the caller: that line is never the one
                // being sent, so its send goes on.
                const isWaitingForIt =
                    existingPaymentLine?.transaction_id === molliePayment.id &&
                    existingPaymentLine.payment_status === "waitingCard";
                if (isWaitingForIt) {
                    paymentInterface.handleMollieStatusResponse(existingPaymentLine, statusMessage);
                }
            }
        }

        // A paid payment came back: an unsent Mollie line was made for an amount due that no longer
        // holds. The cashier adds a new one if something is still due.
        if (addedBack) {
            for (const paymentLine of [...order.payment_ids]) {
                const isMollie = paymentLine.payment_method_id.payment_provider === "mollie";
                if (isMollie && paymentLine.payment_status === "pending") {
                    order.removePaymentline(paymentLine);
                }
            }
        }
        return changed;
    },
});
