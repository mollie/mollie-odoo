/** @odoo-module **/

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    add_paymentline(payment_method) {
        // Prevent adding another Mollie payment line if one already exists
        if (
            payment_method.use_payment_terminal &&
            payment_method.use_payment_terminal.includes('mollie')
        ) {
            const hasMolliePayment = this.pos
            .get_order_list()
            .some(order =>
                order.paymentlines.some(
                line =>
                    line.payment_method &&
                    line.payment_method.use_payment_terminal && !line.is_done() &&
                    line.payment_method.use_payment_terminal.includes('mollie')
                )
            );
            if (hasMolliePayment) {
                return false;
            }
        }
        var result = super.add_paymentline(...arguments);
        if (payment_method.limit_amount && result){
            result.set_amount(payment_method.limit_amount);
        }
        return result;
    }
});
