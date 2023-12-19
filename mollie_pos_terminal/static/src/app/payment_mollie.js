/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { uuidv4 } from "@point_of_sale/utils";
import { ConfirmPopup } from "@point_of_sale/app/utils/confirm_popup/confirm_popup";

export class PaymentMollie extends PaymentInterface {
    /**
     * @override
     */
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
    }

    /**
     * @override
     */
    send_payment_request(cid) {
        super.send_payment_request(cid);
        return this._mollie_pay(cid);
    }

    /**
     * @override
     *
     * At the moment, POS payments are no cancellable from the Mollie API.
     * It can be only cancelled from the terminal itself. If you cancel the
     * transaction from the terminal, we get notification and `handleMollieStatusResponse`
     * will handle cancellation. For force cancellation we show popup then cancel.
     */
    async send_payment_cancel(order, cid) {

        const { confirmed } = await this.env.services.popup.add(ConfirmPopup, {
            title: _t('Cancel mollie payment'),
            body: _t('First cancel transaction on POS device. Only use force cancel if that fails'),
            confirmText: _t('Force Cancel'),
            cancelText: _t('Discard')
        });

        if (confirmed) {
            super.send_payment_cancel(order, cid);
            const paymentLine = this.pending_mollie_line();
            paymentLine.set_payment_status('retry');
            return true;
        }
    }

    set_most_recent_mollie_uid(id) {
        this.most_recent_mollie_uid = id;
    }

    pending_mollie_line() {
        return this.pos.getPendingPaymentLine("mollie");
    }

    _handle_odoo_connection_failure(data = {}) {
        var line = this.pending_mollie_line();
        if (line) {
            line.set_payment_status("retry");
        }
        this._show_error(
            _t("Could not connect to the Odoo server, please check your internet connection and try again.")
        );
        return Promise.reject(data);
    }

    _submit_mollie_payment(data) {
        return this.env.services.orm.silent
            .call('pos.payment.method', 'mollie_payment_request', [
                [this.payment_method.id],
                data
            ]).catch(this._handle_odoo_connection_failure.bind(this));
    }

    _mollie_pay_data() {
        var order = this.pos.get_order();
        var line = order.selected_paymentline;
        this.most_recent_mollie_uid = uuidv4();
        return {
            'mollie_uid': this.most_recent_mollie_uid,
            'description': order.name,
            'order_id': order.uid,
            'curruncy': this.pos.currency.name,
            'amount': line.amount,
            'session_id': this.pos.pos_session.id,
        }
    }

    _mollie_pay(cid) {
        var order = this.pos.get_order();

        if (order.selected_paymentline.amount < 0) {
            this._show_error(_t("Cannot process transactions with negative amount."));
            return Promise.resolve();
        }

        var data = this._mollie_pay_data();
        var line = order.paymentlines.find((paymentLine) => paymentLine.cid === cid);
        line.setMollieUID(this.most_recent_mollie_uid);
        return this._submit_mollie_payment(data).then((data) => {
            return this._mollie_handle_response(data);
        });
    }

    /**
     * This method handles the response that comes from Mollie
     * when we first make a request to pay.
     */
    _mollie_handle_response(response) {
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
        return this.waitForPaymentConfirmation();

    }

    waitForPaymentConfirmation() {
        return new Promise((resolve) => {
            this.paymentLineResolvers[this.pending_mollie_line().cid] = resolve;
        });
    }

    /**
     * This method is called from pos_bus when the payment
     * confirmation from Mollie is received via the webhook.
     */
    async handleMollieStatusResponse() {

        const line = this.pending_mollie_line();
        const paymentStatus = await this.env.services.orm.silent
            .call('mollie.pos.terminal.payments', 'get_mollie_payment_status', [
                []], {
                mollie_uid: line.mollieUID
            })

        if (!paymentStatus) {
            this._handle_odoo_connection_failure();
            return;
        }

        const resolver = this.paymentLineResolvers?.[line.cid];
        if (paymentStatus.status == 'paid') {
            this._resolvePaymentStatus(true);
        } else if (['expired', 'canceled', 'failed'].includes(paymentStatus.status)) {
            this._resolvePaymentStatus(false);
        }
    }

    _resolvePaymentStatus(state) {
        const line = this.pending_mollie_line();
        const resolver = this.paymentLineResolvers?.[line.cid];
        if (resolver) {
            resolver(state);
        } else {
            line.handle_payment_response(state);
        }
    }

    _show_error(msg, title) {
        if (!title) {
            title = _t("Mollie Error");
        }
        this.env.services.popup.add(ErrorPopup, {
            title: title,
            body: msg,
        });
    }
}
