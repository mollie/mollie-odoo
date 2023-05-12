/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useSyncMollieTerminalButton } from "@mollie_pos_terminal/views/sync_terminal_hook";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

export class SyncMollieTerminalListController extends ListController {
    setup() {
        super.setup();
        useSyncMollieTerminalButton();
    }
}

registry.category("views").add("mollie_sync_terminal_tree", {
    ...listView,
    Controller: SyncMollieTerminalListController,
    buttonTemplate: "MollieTerminalListView.buttons",
});
