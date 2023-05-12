/** @odoo-module **/

import { register_payment_method, Payment } from "point_of_sale.models";
import { PaymentMollie } from "@mollie_pos_terminal/js/payment_mollie";
const Registries = require('point_of_sale.Registries');

register_payment_method("mollie", PaymentMollie);

// We are keeping UID per terminal payment line. We are sending this uid in
// metadata of the payment request. This uid will be helpful when we are
// checking payment status.
const PosMolliePayment = (Payment) => class PosMolliePayment extends Payment {
    constructor(obj, options) {
        super(...arguments);
        this.mollieUID = this.mollieUID || null;
    }
    //@override
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.mollie_uid = this.mollieUID;
        return json;
    }
    //@override
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.mollieUID = json.mollie_uid;
    }
    setMollieUID(id) {
        this.mollieUID = id;
    }
}
Registries.Model.extend(Payment, PosMolliePayment);