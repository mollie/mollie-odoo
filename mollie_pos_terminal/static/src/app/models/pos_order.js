/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    /**
     * What can still be paid with a Mollie voucher method: the order's lines of its voucher
     * category, minus every payment line of that category (whatever its status), except
     * `exceptLine` (the line being edited or sent).
     */
    getMollieVoucherRemaining(voucherMethod, exceptLine = null) {
        const category = voucherMethod.mollie_voucher_category;
        const eligible = this.lines
            .filter((line) => line.product_id.mollie_voucher_category === category)
            .reduce((sum, line) => sum + line.priceIncl, 0);
        const committed = this.payment_ids
            .filter(
                (paymentLine) =>
                    paymentLine !== exceptLine &&
                    paymentLine.payment_method_id.isMollieVoucher &&
                    paymentLine.payment_method_id.mollie_voucher_category === category
            )
            .reduce((sum, paymentLine) => sum + paymentLine.amount, 0);
        return Math.max(0, this.currency.round(eligible - committed));
    },

    /**
     * @override
     *
     * Never default a voucher above what it can still pay.
     */
    getDefaultAmountDueToPayIn(paymentMethod) {
        const amount = super.getDefaultAmountDueToPayIn(...arguments);
        if (paymentMethod.isMollieVoucher) {
            return Math.min(amount, this.getMollieVoucherRemaining(paymentMethod));
        }
        return amount;
    },
});
