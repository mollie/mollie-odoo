/** @odoo-module */

import { PosPaymentMethod } from "@point_of_sale/app/models/pos_payment_method";
import { patch } from "@web/core/utils/patch";

patch(PosPaymentMethod.prototype, {
    /**
     * A Mollie voucher method (meal, eco, gift...). The category alone is not enough: it stays on a
     * method whose provider was changed afterwards.
     */
    get isMollieVoucher() {
        return this.payment_provider === "mollie" && Boolean(this.mollie_voucher_category);
    },
});
