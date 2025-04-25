/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    getDefaultAmountDueToPayIn(paymentMethod) {
        const result = super.getDefaultAmountDueToPayIn(...arguments);
        if (paymentMethod.limit_amount){
            return paymentMethod.limit_amount;
        }
        return result;
    }
});
