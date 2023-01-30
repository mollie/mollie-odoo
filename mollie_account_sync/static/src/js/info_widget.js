/** @odoo-module **/

import { registry } from "@web/core/registry";
const { Component, xml } = owl;
import { useService } from "@web/core/utils/hooks";
import { Dialog } from '@web/core/dialog/dialog';
export class MollieJsonDataTable extends Component {
    setup() {
        super.setup();
    }
    formatCamelCase(text) {
        var result = text.replace(/([A-Z])/g, " $1");
        return result.charAt(0).toUpperCase() + result.slice(1);
    }
    get tableVal() {
        return JSON.parse(this.props.value);
    }
}
MollieJsonDataTable.components = { Dialog }
MollieJsonDataTable.template = 'drg_payment_info';
export class mollieJsonDataComponent extends Component {
    setup() {
        this.dialogs = useService("dialog");
        this.data = JSON.parse(this.props.value);
        super.setup();
    }
    _openDialog() {
        this.dialogs.add(MollieJsonDataTable, this.props);
    }
}
mollieJsonDataComponent.template = "mollieAccountSync.mollieJsonDataComponent";
mollieJsonDataComponent.supportedTypes = ["char"];
mollieJsonDataComponent.components = ["MollieJsonDataTable"];
registry.category("fields").add("payment_info", mollieJsonDataComponent);
