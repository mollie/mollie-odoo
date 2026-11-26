/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";

patch(PaymentScreenPaymentLines.prototype, {
    getPaymentActionState(line) {
        const state = super.getPaymentActionState(line);
        const isMollie = line?.payment_method_id?.payment_provider === "mollie";

        if (isMollie && ["waitingCard", "waitingScan", "waiting"].includes(line.payment_status)) {
            // Never Force done: only Mollie's answer settles the line. Check Status only once the
            // payment exists at Mollie: while it is being sent (`waiting`), the sync leaves the line
            // to its request.
            state.actions = state.actions.filter((action) => action.id !== "force_done");
            if (line.payment_status !== "waiting") {
                state.actions.unshift({
                    id: "check_status",
                    label: _t("Check Status"),
                    title: _t("Check Payment Status"),
                    action: () =>
                        this.pos
                            .syncMollieOrder(line.pos_order_id)
                            .catch((error) => line.payment_interface._showMollieError(error)),
                    severity: "primary",
                });
            }
        }
        if (isMollie) {
            if (state.id === "refund_available") {
                state.title = _t("This will also refund the amount via Mollie");
            }
            for (const action of state.actions) {
                if (action.id === "refund") {
                    action.label = _t("Refund via Mollie");
                }
                if (action.id === "cancel") {
                    // Cancel removes the line, as Delete does: no line is left in Retry on a payment
                    // the customer may still pay. If paid, it comes back as its own line (see
                    // syncMollieOrder).
                    action.action = () => this.props.deleteLine(line.uuid);
                }
            }
        }

        return state;
    },
});
