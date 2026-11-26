/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PaymentMollie } from "@pos_mollie/payment_mollie";

patch(PaymentMollie.prototype, {
    /**
     * @override
     *
     * Send the order's uuid with a new payment: a paid payment then finds its order even when its
     * line was removed (see `mollie_get_order_payments`).
     */
    async callPaymentMethod(method, params) {
        if (method === "mollie_create_payment") {
            const line = this.pos.models["pos.payment"].getBy("uuid", params[2]);
            params = [...params, line?.pos_order_id?.uuid];
        }
        return super.callPaymentMethod(method, params);
    },

    /**
     * @override
     *
     * Show the line as waiting for the card while the customer pays: that state offers Cancel.
     */
    _waitForPaymentConfirmation(paymentLine) {
        paymentLine.setPaymentStatus("waitingCard");
        return super._waitForPaymentConfirmation(...arguments);
    },

    /**
     * @override
     *
     * Mollie can't cancel a terminal payment, so the cashier cancels it on the terminal. Force
     * cancel assumes that was done: it stops waiting without calling Mollie. In the POS the line is
     * then removed (see payment_lines.js); the kiosk removes it itself.
     */
    async sendPaymentCancel(line) {
        const confirmed = await ask(this.env.services.dialog, {
            title: _t("Cancel mollie payment"),
            body: _t("First cancel transaction on POS device. Only use force cancel if that fails"),
            confirmLabel: _t("Force Cancel"),
            cancelLabel: _t("Discard"),
        });
        if (!confirmed) {
            return false;
        }
        const resolve = this.paymentLineResolvers[line.uuid];
        if (resolve) {
            this.paymentLineResolvers[line.uuid] = null;
            resolve(false);
        }
        return true;
    },

    /**
     * @override
     *
     * Refund the original Mollie payment made with the same method: an order can be paid by voucher
     * and by card. Without one, as `pos_mollie` does.
     */
    _findOriginalPaymentId(refundPaymentLine) {
        const refundedOrder = refundPaymentLine.pos_order_id.lines[0]?.refunded_orderline_id?.order_id;
        const original = refundedOrder?.payment_ids.find(
            (line) => line.payment_method_id.id === refundPaymentLine.payment_method_id.id && line.transaction_id
        );
        return original?.transaction_id ?? super._findOriginalPaymentId(...arguments);
    },

    /**
     * Make the line follow a Mollie payment, at the amount that payment is for: the line may have
     * been edited since the request, and the customer pays what the terminal shows.
     */
    _followMolliePayment(line, payment) {
        line.transaction_id = payment.id;
        const amount = parseFloat(payment.amount.value);
        if (!line.pos_order_id.currency.isZero(amount - line.amount)) {
            line.setAmount(amount);
            const formattedAmount = this.pos.formatCurrency(amount);
            this.env.services.notification.add(
                payment.status === "paid"
                    ? _t("The customer paid %s on the terminal: the line was set to that amount.", formattedAmount)
                    : _t("The terminal asks %s: the line was set to that amount.", formattedAmount),
                { type: "warning" }
            );
        }
    },

    /**
     * The status message `handleMollieStatusResponse` expects, built from a Mollie payment the
     * same way `pos_mollie`'s polling builds it.
     */
    _mollieStatusMessage(payment) {
        return {
            status: payment.status,
            card_no: payment.details?.cardNumber,
            card_type: payment.details?.cardFunding,
            card_brand: payment.details?.cardLabel,
            status_reason: payment.statusReason,
        };
    },
});
