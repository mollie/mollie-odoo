/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useSyncMolliePaymentsTerminalButton } from "@mollie_sales_invoice_terminal_payments/views/sync_terminal_hook";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

export class SyncMollieTerminalListController extends ListController {
    setup() {
        super.setup();
        useSyncMolliePaymentsTerminalButton();
    }
}

registry.category("views").add("mollie_payments_sync_terminal_tree", {
    ...listView,
    Controller: SyncMollieTerminalListController,
    buttonTemplate: "MolliePaymentsTerminalListView.buttons",
});
