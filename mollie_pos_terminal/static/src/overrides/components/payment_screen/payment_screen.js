/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
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
            this.currentOrder.set_partner(partner);
        }

        return super._isOrderValid(...arguments)
    }

});
