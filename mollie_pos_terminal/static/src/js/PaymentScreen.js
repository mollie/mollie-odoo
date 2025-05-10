odoo.define('mollie_pos_terminal.PaymentScreen', function(require) {
    "use strict";

    const PaymentScreen = require('point_of_sale.PaymentScreen');
    const Registries = require('point_of_sale.Registries');
    const NumberBuffer = require('point_of_sale.NumberBuffer');
    const { onMounted } = owl;
    var utils = require('web.utils');

    var round_pr = utils.round_precision;

    const PosMolliePaymentScreen = PaymentScreen => class extends PaymentScreen {
        setup() {
        super.setup();
            onMounted(() => {
                const pendingPaymentLine = this.currentOrder.paymentlines.find(
                    paymentLine => paymentLine.payment_method.use_payment_terminal === 'mollie' &&
                        (!paymentLine.is_done() && paymentLine.get_payment_status() == 'waitingCard')
                );
                if (pendingPaymentLine) {
                    const paymentTerminal = pendingPaymentLine.payment_method.payment_terminal;
                    paymentTerminal.set_most_recent_mollie_uid(pendingPaymentLine.mollieUID);
                    pendingPaymentLine.set_payment_status('waitingCard');
                    paymentTerminal.start_mollie_status_polling().then(isPaymentSuccessful => {
                        if (isPaymentSuccessful) {
                            pendingPaymentLine.set_payment_status('done');
                        } else {
                            pendingPaymentLine.set_payment_status('retry');
                        }
                    });
                }
            });
        }
        async _isOrderValid(isForceValidate) {

            let mollieLine = this.currentOrder.paymentlines.find(
                (paymentLine) => paymentLine.payment_method.use_payment_terminal === "mollie"
            );

            mollieLine = this.currentOrder.paymentlines[0];

            if (mollieLine
                && mollieLine.payment_method.split_transactions
                && mollieLine.payment_method.mollie_payment_default_partner
                && !this.currentOrder.get_partner()) {
                var partner = this.env.pos.db.get_partner_by_id(mollieLine.payment_method.mollie_payment_default_partner[0]);
                this.currentOrder.set_partner(partner);
            }

            return super._isOrderValid(...arguments)
        }
        getVoucherAmounts(pm, order) {
            const voucherAmount = round_pr(order.get_orderlines().reduce((sum, line) =>
                line.product.mollie_voucher_category === pm.mollie_voucher_category
                    ? sum + (line.get_display_price())
                    : sum, 0), this.env.pos.currency.rounding);

            const totalPaid = round_pr(order.paymentlines.reduce((sum, payment) =>
                payment.payment_method.id === pm.id && payment.payment_status === 'done'
                    ? sum + payment.amount
                    : sum, 0), this.env.pos.currency.rounding);

            return { voucherAmount, totalPaid };
        }
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
        }
        getVoucherAmountDisplayText(pm) {
            // TODO: Need to improve this function.
            const order = this.currentOrder;
            const { voucherAmount, totalPaid } = this.getVoucherAmounts(pm, order);
            const remaining = voucherAmount - totalPaid;
            pm.limit_amount = remaining;
            return `(${this.env.pos.format_currency(remaining)})`;

        }
        _updateSelectedPaymentline() {
            if (!this.selectedPaymentLine) return; // do nothing if no selected payment line
            var amount
            if (NumberBuffer.get() === null) {
                amount=0;
            }
            else {
                amount = NumberBuffer.getFloat();
            }
            if (this.selectedPaymentLine.payment_method.mollie_voucher_category && amount > this.selectedPaymentLine.payment_method.limit_amount) {
                this.showPopup('ErrorPopup', {
                    title: this.env._t("Error"),
                    body: this.env._t("Amount exceeds the limit amount of the Voucher."),
                });
                return false;
            }
            return super._updateSelectedPaymentline(...arguments);
        }
    };

    Registries.Component.extend(PaymentScreen, PosMolliePaymentScreen);

    return PaymentScreen;
});
