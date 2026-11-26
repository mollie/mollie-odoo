/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosPaymentMethodPlugin } from "@point_of_sale/app/plugins/pos_payment_method_plugin";

patch(PosPaymentMethodPlugin.prototype, {
    /**
     * @override
     *
     * Voucher methods keep their own button, outside the Mollie group.
     */
    computeDefaultGroups() {
        const groups = super.computeDefaultGroups();
        const mollieMethods = groups.mollie?.filter((paymentMethod) => !paymentMethod.isMollieVoucher);
        if (mollieMethods?.length > 1) {
            groups.mollie = mollieMethods;
        } else {
            delete groups.mollie;
        }
        return groups;
    },
});
