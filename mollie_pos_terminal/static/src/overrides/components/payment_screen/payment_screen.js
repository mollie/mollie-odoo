/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { markup } from "@odoo/owl";

patch(PaymentScreenPaymentLines, {
    props: {
        ...PaymentScreenPaymentLines.props,
        sendMollieStatusCheck: { type: Function, optional: true },
    },
});

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const pendingPaymentLine = this.currentOrder.payment_ids.find(
                (paymentLine) =>
                    paymentLine.payment_method_id.use_payment_terminal === "mollie" &&
                    !paymentLine.is_done() &&
                    paymentLine.get_payment_status() !== "pending"
            );
            if (!pendingPaymentLine) {
                return;
            }

            pendingPaymentLine.payment_method_id.payment_terminal.set_most_recent_mollie_uid(
                pendingPaymentLine.mollieUID
            );
        });
    },

    async _isOrderValid(isForceValidate) {

        let mollieLine = this.currentOrder.payment_ids.find(
            (paymentLine) => paymentLine.payment_method_id.use_payment_terminal === "mollie"
        );

        mollieLine = this.currentOrder.payment_ids[0];
        if (mollieLine
            && mollieLine.payment_method_id.split_transactions
            && mollieLine.payment_method_id.mollie_payment_default_partner
            && !this.currentOrder.get_partner()) {
            var partner = mollieLine.payment_method_id.mollie_payment_default_partner['id']
            this.currentOrder.set_partner(partner);
        }

        return super._isOrderValid(...arguments)
    },

    async sendMollieStatusCheck(line) {
        const payment_terminal = line.payment_method_id.payment_terminal;
        line.set_payment_status("waiting");
        await payment_terminal.send_mollie_status_check(
            this.currentOrder,
            line.cid
        );
        if (line.payment_status == 'waiting') {
            line.set_payment_status("waitingCard");
        }
    },

    async addNewPaymentLine(paymentMethod) {
        let refundOrderId = false;
        for (let line of this.currentOrder.lines) {
            refundOrderId = line?.refunded_orderline_id?.raw?.order_id || false;
            if (refundOrderId) {
                break;
            }
        }

        if (this.currentOrder.get_due() >= 0 || paymentMethod.use_payment_terminal != 'mollie' || refundOrderId == false) {
            return await super.addNewPaymentLine(...arguments);
        }

        const OriginPaymentDetails = await this.env.services.orm.silent
            .call('pos.order', 'get_mollie_payment_details', [
                refundOrderId, this.pos.session.id]);

        if (!OriginPaymentDetails) {
            this.env.services.dialog.add(AlertDialog, {
                title: "Error",
                body: _t("You can only refund mollie order with this method."),
            });
            return false;
        }

        if (OriginPaymentDetails.amount_remaining < -this.currentOrder.get_due()) {
            this.env.services.dialog.add(AlertDialog, {
                title: _t("Refund limit reached"),
                body: markup(`
                    <div class="d-flex flex-column align-items-center">
                    <img style="max-width: 120px;" src="/mollie_pos_terminal/static/src/img/warning.svg" class="img img-fluid mb-2"/>
                        <b class="text-muted small mb-1"> You are trying to refund </b>
                        <b class="text-warning"> ${ this.env.utils.formatCurrency(-this.currentOrder.get_due()) } </b> <b class="text-muted small mt-1"> Maximum possible amount for refund is </b>
                        <h1 class="mb-0 mt-2" style="font-size: clamp(24px, 2vw, 64px);"><b>${this.env.utils.formatCurrency(OriginPaymentDetails.amount_remaining)}</b></h1>
                    </div>
                `),
                size: 'md'
            });
            return false;
        }

        return new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Mollie Refund"),
                body: markup(`
                    <div class="d-flex flex-column align-items-center">
                        <img style="max-width: 120px;" src="/mollie_pos_terminal/static/src/img/mollie-refund.svg" class="img img-fluid mb-2"/>
                        <b class="text-muted"> To refund in mollie </b>
                        <h1 class="mb-0" style="font-size: clamp(24px, 2vw, 64px);"> <b>${this.env.utils.formatCurrency(this.currentOrder.get_due())}</b></h1>
                        <small class="text-muted"> (Total <b>${this.env.utils.formatCurrency(OriginPaymentDetails.amount_remaining) } </b> available for refund) </small>
                        <div class="text-muted small d-flex w-75 mt-5">
                            <i style="color: #FFC107;" class="fa fa-exclamation-triangle pt-1 pe-2" aria-hidden="true"></i>
                            <span>Refunding here will also process the refund through Mollie, and the amount will be credited back to the customer.</span></div>
                    </div>
                `),
                confirm: async () => {
                    resolve(await super.addNewPaymentLine(...arguments));
                },
                confirmLabel: _t("Refund"),
                cancel: () => { },
                cancelLabel: _t("Discard"),
            }, {
                onClose: resolve.bind(null, false),
            });
        });

    },

    updateSelectedPaymentline(amount = false) {
        if (!this.selectedPaymentLine) {
            return;
        } // do nothing if no selected payment line
        if (amount === false) {
            if (this.numberBuffer.get() === null) {
                amount = null;
            } else if (this.numberBuffer.get() === "") {
                amount = 0;
            } else {
                amount = this.numberBuffer.getFloat();
            }
        }
        if (this.selectedPaymentLine.payment_method_id.mollie_voucher_category && amount > this.selectedPaymentLine.payment_method_id.limit_amount) {
            this.dialog.add(AlertDialog, {
                title: _t("Error"),
                body: _t("Amount exceeds the limit amount of the Voucher."),
            });
            return false;
        }
        return super.updateSelectedPaymentline(...arguments);
    },

});
