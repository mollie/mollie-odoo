/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { uuidv4 } from "@point_of_sale/utils";
import { ConfirmationDialog, AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

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
    send_payment_request(uuid) {
        super.send_payment_request(uuid);
        return this._mollie_pay(uuid);
    }

    /**
     * @override
     *
     * At the moment, POS payments are no cancellable from the Mollie API.
     * It can be only cancelled from the terminal itself. If you cancel the
     * transaction from the terminal, we get notification and `handleMollieStatusResponse`
     * will handle cancellation. For force cancellation we show popup then cancel.
     */
    async send_payment_cancel(order, uuid) {

        this.env.services.dialog.add(ConfirmationDialog, {
            title: _t('Cancel mollie payment'),
            body: _t('First cancel transaction on POS device. Only use force cancel if that fails'),
            confirmLabel: _t('Force Cancel'),
            confirm: () => {
                super.send_payment_cancel(...arguments);
                const paymentLine = this.pending_mollie_line();
                paymentLine.set_payment_status('retry');
                return true;
            },
            cancelLabel: _t('Discard'),
            cancel: () => { },
        });
    }

    /**
     * In some cases, websocket does not send update about mollie webhook.
     * e.g. One case we found is parallel order.
     * This will check payment status in case webhook status update via bus is missed.
     */
    async send_mollie_status_check(order, cid) {
        await this.handleMollieStatusResponse();
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
                [this.payment_method_id.id],
                data
            ]).catch(this._handle_odoo_connection_failure.bind(this));
    }

    _mollie_pay_data(params) {
        var order = this.pos.get_order();
        var line = order.get_selected_paymentline();
        this.most_recent_mollie_uid = uuidv4()

        return {
            ...params,
            'mollie_uid': this.most_recent_mollie_uid,
            'description': order.name,
            'order_id': order.uuid,
            'curruncy': this.pos.currency.name,
            'amount': line.amount,
            'session_id': this.pos.session.id,
            'payment_method_id': this.payment_method_id.id,
            'mollie_voucher_category': this.payment_method_id.mollie_voucher_category,
        }
    }

    async _mollie_pay(uuid) {
        var order = this.pos.get_order();
        let params = {};
        let mollie_origin_transaction_id = false;
        if (order.get_selected_paymentline().amount < 0) {
            let refundOrderId = false;
            for (let line of order.lines) {
                refundOrderId = line?.refunded_orderline_id?.raw?.order_id || false;
                if (refundOrderId) {
                    break;
                }
            }
            mollie_origin_transaction_id = await this.env.services.orm.silent
                .call('pos.order', 'get_mollie_transection_id', [
                        refundOrderId, this.pos.session.id]);
            if (mollie_origin_transaction_id) {
                params['mollie_origin_transaction_id'] = mollie_origin_transaction_id;
            }
        }

        var data = this._mollie_pay_data(params);
        var line = order.payment_ids.find((paymentLine) => paymentLine.uuid === uuid);
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
        // manage refunds
        if (response.status == 'pending' && line.amount < 0) {
            line.set_payment_status('waitingCard');
            return Promise.resolve(true);
        }
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
            this.paymentLineResolvers[this.pending_mollie_line().uuid] = resolve;
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

        const resolver = this.paymentLineResolvers?.[line.uuid];
        if (paymentStatus.status == 'paid') {
            this._resolvePaymentStatus(true);
        } else if (['expired', 'canceled', 'failed'].includes(paymentStatus.status)) {
            this._resolvePaymentStatus(false);
        }
    }

    _resolvePaymentStatus(state) {
        const line = this.pending_mollie_line();
        const resolver = this.paymentLineResolvers?.[line.uuid];
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
        this.env.services.dialog.add(AlertDialog, {
            title: title,
            body: msg,
        });
    }
}
