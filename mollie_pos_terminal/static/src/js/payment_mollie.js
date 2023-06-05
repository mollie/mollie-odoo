/** @odoo-module alias=mollie_pos_terminal.payment **/

var rpc = require('web.rpc');
import PaymentInterface from "point_of_sale.PaymentInterface";
import { Gui } from "point_of_sale.Gui"
import { _t } from "@web/core/l10n/translation";

class UuidGenerator {
    constructor() {
        this.isFastIdStrategy = false;
        this.fastIdStart = 0;
    }
    setIsFastStrategy(isFast) {
        this.isFastIdStrategy = isFast;
    }
    uuidv4() {
        if (this.isFastIdStrategy) {
            this.fastIdStart++;
            return String(this.fastIdStart);
            //@ts-ignore
        }
        else if (window.crypto && window.crypto.getRandomValues) {
            //@ts-ignore
            return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
        }
        else {
            // mainly for jest and other browsers that do not have the crypto functionality
            return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
                var r = (Math.random() * 16) | 0, v = c == "x" ? r : (r & 0x3) | 0x8;
                return v.toString(16);
            });
        }
    }
}

var uuidGenerator = new UuidGenerator()

const PaymentMollie = PaymentInterface.extend({
    send_payment_request: function (cid) {
        this._super.apply(this, arguments);
        this._reset_state();

        var order = this.pos.get_order();
        if (order.selected_paymentline.amount <= 0) {
            this._show_error(_t('Cannot process transactions with negative or zero amount.'));
            return Promise.resolve();
        }

        if (order === this.poll_error_order) {
            delete this.poll_error_order;
            return this._mollie_handle_response({'status': 'open'});
        }

        var mollie_data = this._prepare_mollie_pay_data(order);
        var line = order.paymentlines.find(paymentLine => paymentLine.cid === cid);
        line.setMollieUID(this.most_recent_mollie_uid);
        return this._create_mollie_payment(mollie_data).then((data) => {
            return this._mollie_handle_response(data);
        });
    },

    _prepare_mollie_pay_data: function (order) {
        var line = order.selected_paymentline;
        this.most_recent_mollie_uid = uuidGenerator.uuidv4();
        return {
            'mollie_uid': this.most_recent_mollie_uid,
            'description': order.name,
            'order_id': order.uid,
            'curruncy': this.pos.currency.name,
            'amount': line.amount,
        }
    },

    _create_mollie_payment: function (data) {
        return rpc.query({
            model: 'pos.payment.method',
            method: 'mollie_payment_request',
            args: [[this.payment_method.id], data],
        }, {
            shadow: true,
        }).catch(this._handle_odoo_connection_failure.bind(this));
    },

    send_payment_cancel: function (order, cid) {
        Gui.showPopup('ConfirmPopup', {
            title: _t('Cancel mollie payment'),
            body: _t('First cancel transaction on POS device. Only use force cancel if that fails'),
            confirmText: _t('Force Cancel'),
            cancelText: _t('OK'),
        }).then((result) => {
            if (result.confirmed) {
                var line = order.paymentlines.find(paymentLine => paymentLine.cid === cid);
                line.set_payment_status('retry');
            }
        });
        return false;
    },

    close: function () {
        this._super.apply(this, arguments);
    },

    set_most_recent_mollie_uid(id) {
        this.most_recent_mollie_uid = id;
    },

    _show_error: function (msg) {
        Gui.showPopup('ErrorPopup', {
            'title': _t('Mollie Error'),
            'body': msg,
        });
    },

    pending_mollie_line(order) {
        order = order || this.pos.get_order();
        return order && order.paymentlines.find(
            paymentLine => paymentLine.payment_method.use_payment_terminal === 'mollie' && (!paymentLine.is_done()));
    },

    _mollie_handle_response: function (response) {
        var line = this.pending_mollie_line();
        if (response.status != 'open') {
            this._show_error(response.detail);
            line.set_payment_status('retry');
            return Promise.resolve();
        }
        if (response.id) {
            line.transaction_id = response.id;
        }
        line.set_payment_status('waitingCard');
        return this.start_mollie_status_polling()
    },

    _handle_odoo_connection_failure: function (data) {
        // handle timeout
        var line = this.pending_mollie_line();
        if (line) {
            line.set_payment_status('retry');
        }
        this._show_error(_t('Could not connect to the Odoo server, please check your internet connection and try again.'));
        return Promise.reject(data);
    },

    start_mollie_status_polling() {
        var res = new Promise((resolve, reject) => {
            clearInterval(this.polling);
            this._poll_for_response(resolve, reject);
            this.polling = setInterval(() => {
                this._poll_for_response(resolve, reject);
            }, 5500);
        });

        res.finally(() => {
            this._reset_state();
        });

        return res;
    },

    _poll_for_response: function (resolve, reject) {
        var line = this.pending_mollie_line();
        if (!line) {
            return resolve(false);
        }
        return rpc.query({
            model: 'mollie.pos.terminal.payments',
            method: 'get_mollie_payment_status',
            args: [],
            kwargs: { mollie_uid: line.mollieUID }
        }, {
            timeout: 5000,
            shadow: true,
        }).catch((data) => {
            if (this.remaining_polls != 0) {
                this.remaining_polls--;
            } else {
                reject();
                this.poll_error_order = this.pos.get_order();
                return this._handle_odoo_connection_failure(data);
            }
            return Promise.reject(data);
        }).then(function (data) {
            if (data.status == 'paid') {
                resolve(true);
            } else if (data.status == 'expired') {
                line.set_payment_status('retry');
                reject();
            } else if (data.status == 'canceled') {
                resolve(false);
            } else if(data.status == 'failed') {
                resolve(false);
            }
        });
    },

    _reset_state: function () {
        this.remaining_polls = 4;
        clearInterval(this.polling);
    },
});

export default PaymentMollie;