/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    /**
     * @override
     *
     * Record what happened at Mollie while the POS was away (also after a reload, which mounts
     * this screen again), e.g. the paid payment of a removed line. In the background: the screen
     * doesn't wait for it.
     */
    onMounted() {
        super.onMounted(...arguments);
        this.pos.syncMollieOrder(this.currentOrder).catch(() => {});
    },

    /**
     * @override
     *
     * A voucher method shows only while it can still pay part of the order, and never on a refund.
     */
    showPaymentMethod(paymentMethod) {
        if (
            paymentMethod.isMollieVoucher &&
            (this.isRefundOrder || !this.currentOrder.getMollieVoucherRemaining(paymentMethod))
        ) {
            return false;
        }
        return super.showPaymentMethod(...arguments);
    },

    /**
     * @override
     *
     * A voucher can't pay more than the order's lines of its category: refuse it before it reaches
     * the terminal, and leave the line as is so its amount can be fixed.
     *
     * Before charging the customer, record or wait for what the order already has at Mollie (see
     * `syncMollieOrder`): a removed line's payment may have been paid meanwhile, and on a Retry the
     * line's earlier attempt may have been paid, or still be open on the terminal. If a line
     * changed, nothing is sent: the cashier sees it first.
     */
    async sendPaymentRequest(line) {
        const paymentMethod = line.payment_method_id;
        const order = line.pos_order_id;
        if (paymentMethod.isMollieVoucher) {
            const remaining = order.getMollieVoucherRemaining(paymentMethod, line);
            if (order.currency.isPositive(line.amount - remaining)) {
                this.dialog.add(AlertDialog, {
                    title: _t("Voucher amount too high"),
                    body: _t("This voucher can pay at most %s of this order.", this.pos.formatCurrency(remaining)),
                });
                return;
            }
        }
        if (paymentMethod.payment_provider === "mollie" && line.amount > 0) {
            const statusBeforeSync = line.payment_status;
            try {
                if (await this.pos.syncMollieOrder(order)) {
                    return;
                }
            } catch (error) {
                // Unknown whether an earlier attempt was paid: don't charge again.
                paymentMethod.payment_interface._showMollieError(error);
                return;
            }
            if (line.payment_status !== statusBeforeSync || !order.payment_ids.includes(line)) {
                return; // sent by another click, or deleted, meanwhile
            }
            // A late notification about an earlier attempt must not settle the new one.
            line.transaction_id = false;
        }
        return super.sendPaymentRequest(...arguments);
    },
});
