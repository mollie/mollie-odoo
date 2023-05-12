/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";

const { useComponent } = owl;

export function useSyncMollieTerminalButton() {
    const component = useComponent();
    const action = useService("action");

    component.onClickSyncMollieTerminal = () => {
        action.doAction({
            name: "Sync Terminal",
            type: "ir.actions.act_window",
            res_model: "sync.mollie.terminal",
            target: "new",
            views: [[false, "form"]],
            context: { is_modal: true },
            }, {
                onClose: async () => {
                    await component.model.load();
                    component.model.notify();
                },
        });
    };
}
