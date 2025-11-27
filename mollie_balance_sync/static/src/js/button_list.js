/** @odoo-module **/

import { BankRecButtonList } from "@account_accountant/components/bank_reconciliation/button_list/button_list";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { MollieBalanceJsonDataTable } from "@mollie_balance_sync/js/info_widget";

patch(BankRecButtonList.prototype, {
    async openPaymentInfo(){
        this.addDialog(MollieBalanceJsonDataTable, {
            mollie_balance_json_info: JSON.parse(this.statementLineData.mollie_balance_json_info),
        });
    },
    /* The `get buttonsToDisplay()` method is overriding the existing method in the `BankRecButtonList`
    class. It is adding additional buttons to be displayed based on the `mollie_balance_json_info`
    data present in the `statementLineData`. */
    get buttonsToDisplay() {
        const buttonsToDisplay = super.buttonsToDisplay;
        if (!this.statementLineData.mollie_balance_json_info) {
            return buttonsToDisplay;
        }

        const isValidCondition = (this.props.isTopLine && this.ui.size > 3) ||
                                 (!this.props.isTopLine && this.ui.size <= 3);

        if (!isValidCondition) {
            return buttonsToDisplay;
        }

        const mollieInfo = JSON.parse(this.statementLineData.mollie_balance_json_info);
        const type = mollieInfo?.MollieType;

        if (!type) {
            return buttonsToDisplay;
        }

        const buttonConfig = {
            payment: { class: "text-success mollie_payment_btn", name: _t("Payment") },
            refund: { class: "text-danger mollie_refund_btn", name: _t("Refund") },
            chargeback: { class: "text-danger mollie_chargeback_btn", name: _t("Chargeback") },
            capture: { class: "text-info mollie_capture_btn", name: _t("Capture") },
        };

        if (buttonConfig[type]) {
            buttonsToDisplay.push({
                label: buttonConfig[type].name,
                action: this.openPaymentInfo.bind(this),
                classes: `btn btn-sm py-0 ${buttonConfig[type].class}`,
            });
        }

        return buttonsToDisplay;
    },
});
