/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";

const { useComponent } = owl;

export function useSyncMolliePaymentsTerminalButton() {
    const component = useComponent();
    const action = useService("action");

    component.onClickSyncMolliePaymentsTerminal = () => {
        action.doAction({
            name: "Sync Terminal",
            type: "ir.actions.act_window",
            res_model: "sync.mollie.payments.terminal",
            target: "new",
            views: [[false, "form"]],
            context: {
                is_modal: true,
                default_mollie_provider_id: component.props.context?.default_mollie_provider_id || false
            },
        },
        {
            onClose: async () => {
                await component.model.load();
                component.model.notify();
            },
        });
    };
}
