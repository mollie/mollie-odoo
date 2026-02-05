/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import {
    roundPrecision as round_pr,
} from "@web/core/utils/numbers";
import { onMounted } from "@odoo/owl";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const pendingPaymentLine = this.currentOrder.paymentlines.find(
                (paymentLine) =>
                    paymentLine.payment_method.use_payment_terminal === "mollie" &&
                    !paymentLine.is_done() &&
                    paymentLine.get_payment_status() !== "pending"
            );
            if (!pendingPaymentLine) {
                return;
            }
            pendingPaymentLine.payment_method.payment_terminal.set_most_recent_mollie_uid(
                pendingPaymentLine.mollieUID
            );
        });
    },

    async _isOrderValid(isForceValidate) {

        let mollieLine = this.currentOrder.paymentlines.find(
            (paymentLine) => paymentLine.payment_method.use_payment_terminal === "mollie"
        );

        mollieLine = this.currentOrder.paymentlines[0];

        if (mollieLine
            && mollieLine.payment_method.split_transactions
            && mollieLine.payment_method.mollie_payment_default_partner
            && !this.currentOrder.get_partner()) {
            var partner = this.pos.db.get_partner_by_id(mollieLine.payment_method.mollie_payment_default_partner[0]);
            var pricelist = this.currentOrder.pricelist;
            this.currentOrder.set_partner(partner);
            if (pricelist) {
                this.currentOrder.set_pricelist(pricelist);
            }
        }

        return super._isOrderValid(...arguments)
    },

    async sendMollieStatusCheck(line) {
        const payment_terminal = line.payment_method.payment_terminal;
        line.set_payment_status("waiting");
        await payment_terminal.send_mollie_status_check(
            this.currentOrder,
            line.cid
        );
        if (line.payment_status == 'waiting') {
            line.set_payment_status("waitingCard");
        }
    },

    getVoucherAmounts(pm, order) {
        const voucherAmount = round_pr(order.get_orderlines().reduce((sum, line) =>
            line.product.mollie_voucher_category === pm.mollie_voucher_category
                ? sum + (line.get_price_with_tax())
                : sum, 0), this.pos.currency.rounding);

        const totalPaid = round_pr(order.paymentlines.reduce((sum, payment) =>
            payment.payment_method.id === pm.id && payment.payment_status === 'done'
                ? sum + payment.amount
                : sum, 0), this.pos.currency.rounding);

        return { voucherAmount, totalPaid };
    },

    checkVoucher(pm) {
        // Check whether the payment method is a type of Mollie voucher
        const order = this.currentOrder;
        const isMollieVoucher = pm.use_payment_terminal === 'mollie' &&
            pm.mollie_voucher_category;
        if (!isMollieVoucher) {
            return true;
        }

        // Checked if payment was already completed with the respective method.
        const { voucherAmount, totalPaid } = this.getVoucherAmounts(pm, order);
        if (totalPaid > 0 && voucherAmount === totalPaid) {
            return false;
        }
        // Checks if any order line matches the payment method’s Mollie voucher category.
        return order.get_orderlines().some(
            (line) =>
                line.product.mollie_voucher_category === pm.mollie_voucher_category
        );
    },

    getVoucherAmountDisplayText(pm) {
        // TODO: Need to improve this function.
        const order = this.currentOrder;
        const { voucherAmount, totalPaid } = this.getVoucherAmounts(pm, order);
        const remaining = voucherAmount - totalPaid;
        pm.limit_amount = remaining;
        return `(${this.env.utils.formatCurrency(remaining)})`;

    },

    updateSelectedPaymentline(amount = false) {
        if (!this.selectedPaymentLine) {
            return;
        } // do nothing if no selected payment line
        if (amount === false) {
            if (this.numberBuffer.get() === null) {
                amount = null;
            } else if (this.numberBuffer.get() === "") {
                amount = 0;
            } else {
                amount = this.numberBuffer.getFloat();
            }
        }
        if (this.selectedPaymentLine.payment_method.mollie_voucher_category && amount > this.selectedPaymentLine.payment_method.limit_amount) {
            this.popup.add(ErrorPopup, {
                title: _t("Error"),
                body: _t("Amount exceeds the limit amount of the Voucher."),
            });
            return;
        }
        return super.updateSelectedPaymentline(...arguments);
    },
});
