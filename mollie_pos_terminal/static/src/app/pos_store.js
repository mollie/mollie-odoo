/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("MOLLIE_TERMINAL_RESPONSE", () => {
            let pendingLine = this.getPendingPaymentLine("mollie");
            if (pendingLine) {
                pendingLine.payment_method_id.payment_terminal.handleMollieStatusResponse();
            }
        });
    },
    getVoucherAmounts(pm, order) {
        const taxIncluded = order.config_id.iface_tax_included === "total";
        const voucherAmount = order.get_orderlines().reduce((sum, line) =>
            line.product_id.mollie_voucher_category === pm.mollie_voucher_category
                ? sum + (taxIncluded ? line.price_subtotal_incl : line.price_subtotal)
                : sum, 0);

        const totalPaid = order.payment_ids.reduce((sum, payment) =>
            payment.payment_method_id.id === pm.id && payment.payment_status === 'done'
                ? sum + payment.amount
                : sum, 0);

        return { voucherAmount, totalPaid };
    },
    getVoucherAmountDisplayText(pm, order) {
        // TODO: Need to improve this function.
        const { voucherAmount, totalPaid } = this.getVoucherAmounts(pm, order);
        const remaining = voucherAmount - totalPaid;
        pm.limit_amount = remaining;
        return `(${this.env.utils.formatCurrency(remaining)})`;
    },
    checkVoucher(pm, order) {
        // Check whether the payment method is a type of Mollie voucher
        const isMollieVoucher = pm.use_payment_terminal === 'mollie' &&
            pm.mollie_voucher_category;
        if (!isMollieVoucher) {
            return true;
        }

        // Checked if payment was already completed with the respective method.
        const { voucherAmount, totalPaid } = this.getVoucherAmounts(pm, order);
        if (totalPaid > 0 && voucherAmount === totalPaid){
            return false;
        }

        // Checks if any order line matches the payment method’s Mollie voucher category.
        return order.get_orderlines().some(
            (line) =>
                line.product_id.mollie_voucher_category === pm.mollie_voucher_category
        );
    },
});
