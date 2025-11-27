/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { Dialog } from '@web/core/dialog/dialog';

export class MollieBalanceJsonDataTable extends Component {
    setup() {
        super.setup();
    }
    formatCamelCase(text) {
        var result = text.replace(/([A-Z])/g, " $1");
        return result.charAt(0).toUpperCase() + result.slice(1);
    }
    get tableVal() {
        return this.props.mollie_balance_json_info;
    }
}
MollieBalanceJsonDataTable.components = { Dialog }
MollieBalanceJsonDataTable.template = 'drg_balance_payment_info';
MollieBalanceJsonDataTable.props = {
    mollie_balance_json_info: { type: Object, optional: true },
    close: { type: Function, optional: true },
};

registry.category("dialogs").add("drg_balance_payment_info", MollieBalanceJsonDataTable);
