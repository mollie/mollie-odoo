/** @odoo-module */

import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import {patch} from "@web/core/utils/patch";

patch(OrderPaymentValidation.prototype, {
  async _askForCustomerIfRequired() {
    let mollieLine = this.order.payment_ids.find(
      (paymentLine) => paymentLine.payment_method_id.use_payment_terminal === "mollie"
    );

    mollieLine = this.order.payment_ids[0];
    if (
      mollieLine &&
      mollieLine.payment_method_id.split_transactions &&
      mollieLine.payment_method_id.mollie_payment_default_partner &&
      !this.order.getPartner()
    ) {
      var partner = mollieLine.payment_method_id.mollie_payment_default_partner["id"];
      this.pos.setPartnerToCurrentOrder(partner);
    }
    return super._askForCustomerIfRequired(...arguments);
  },
});
