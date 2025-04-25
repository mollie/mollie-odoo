/** @odoo-module **/

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    add_paymentline(payment_method) {
        var result = super.add_paymentline(...arguments);
        if (payment_method.limit_amount && result){
            result.set_amount(payment_method.limit_amount);
        }
        return result;
    }
});
