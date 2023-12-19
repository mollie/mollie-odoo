/** @odoo-module */
import { register_payment_method } from "@point_of_sale/app/store/pos_store";
import { Payment } from "@point_of_sale/app/store/models";
import { PaymentMollie } from "@mollie_pos_terminal/app/payment_mollie";
import { patch } from "@web/core/utils/patch";

register_payment_method("mollie", PaymentMollie);

patch(Payment.prototype, {
    setup() {
        super.setup(...arguments);
        this.mollieUID = this.mollieUID || null;
    },
    //@override
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        if (json) {
            json.mollie_uid = this.mollieUID;
        }
        return json;
    },
    //@override
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.mollieUID = json.mollie_uid;
    },
    setMollieUID(id) {
        this.mollieUID = id;
    },
});
