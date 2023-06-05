odoo.define('mollie_pos_terminal.models', function (require) {
    var models = require('point_of_sale.models');
    var PaymentMollie = require('mollie_pos_terminal.payment');

    debugger;

    models.register_payment_method('mollie', PaymentMollie);
    models.load_fields('pos.payment.method', 'mollie_pos_terminal_id');

    const superPaymentline = models.Paymentline.prototype;
    models.Paymentline = models.Paymentline.extend({
        initialize: function (attr, options) {
            superPaymentline.initialize.call(this, attr, options);
            this.mollieUID = this.mollieUID || null;
        },
        export_as_JSON: function () {
            const json = superPaymentline.export_as_JSON.call(this);
            json.mollie_uid = this.mollieUID;
            return json;
        },
        init_from_JSON: function (json) {
            superPaymentline.init_from_JSON.apply(this, arguments);
            this.mollieUID = json.mollie_uid;
        },
        setMollieUID: function (id) {
            this.mollieUID = id;
        }
    });

});
