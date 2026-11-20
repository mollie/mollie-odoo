/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useProps, t } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class MollieBalanceJsonDataTable extends Component {
    static components = { Dialog }
    static template = "drg_balance_payment_info";
    props = useProps({
        mollie_balance_json_info: t.object().optional(),
        close: t.function().optional(),
    });
    formatCamelCase(text) {
        var result = text.replace(/([A-Z])/g, " $1");
        return result.charAt(0).toUpperCase() + result.slice(1);
    }
    formatValue(value) {
        return typeof value === "object" && value !== null ? JSON.stringify(value) : value;
    }
    get tableVal() {
        return this.props.mollie_balance_json_info;
    }
}

registry.category("dialogs").add("drg_balance_payment_info", MollieBalanceJsonDataTable);
