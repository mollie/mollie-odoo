import { patch } from "@web/core/utils/patch";
import { SelfOrder } from "@pos_self_order/app/self_order_service";

patch(SelfOrder.prototype, {

    filterPaymentMethods(pms) {
        const pm = super.filterPaymentMethods(...arguments);
        const mollie_pm = pms.filter((rec) => rec.use_payment_terminal === "mollie");
        return [...new Set([...pm, ...mollie_pm])];
    },

});
