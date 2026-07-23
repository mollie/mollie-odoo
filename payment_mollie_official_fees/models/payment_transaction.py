# -*- coding: utf-8 -*-

import logging

from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mollie_fees = fields.Monetary(string="Mollie Fees", currency_field='currency_id', copy=False)

    @api.model_create_multi
    def create(self, values_list):
        """ Add the mollie fees to the transaction based on mollie methods. """
        transactions = super().create(values_list)
        for transaction in transactions:
            sale_order = transaction.sale_order_ids[:1]
            fees_product_id = transaction.provider_id.mollie_fees_product_id
            if transaction.payment_method_id.is_primary:
                payment_method_id = transaction.payment_method_id
            else:
                payment_method_id = transaction.payment_method_id.primary_payment_method_id
            if sale_order and transaction.provider_code == 'mollie' and fees_product_id and payment_method_id.fees_active:
                mollie_untaxed_fees, mollie_taxed_fees = payment_method_id._compute_fees(
                    transaction.amount, transaction.partner_id.country_id, transaction.provider_id, sale_order
                )
                if mollie_taxed_fees:
                    transaction.amount += mollie_taxed_fees
                    transaction.mollie_fees = mollie_untaxed_fees
        return transactions

    def _set_done(self, *, state_message=None, extra_allowed_states=()):
        result = super()._set_done(state_message=state_message, extra_allowed_states=extra_allowed_states)
        if self.provider_code != 'mollie' or not self.mollie_fees:
            return result

        sale_order = self.sale_order_ids[:1]
        if not sale_order:
            return result

        if sale_order.order_line.filtered(lambda line: line.dr_fees_origin_id == self):
            return result

        fees_product = self.provider_id.mollie_fees_product_id
        if not fees_product:
            _logger.warning(
                "Fees of %(fees)s were charged on Mollie transaction %(reference)s but no Mollie "
                "Fees Product is set on provider %(provider)s. The fee line must be added manually "
                "on order %(order)s.",
                {
                    'fees': self.mollie_fees,
                    'reference': self.reference,
                    'provider': self.provider_id.name,
                    'order': sale_order.name,
                },
            )
            return result

        self.env['sale.order.line'].create({
            'product_id': fees_product.id,
            'product_uom_qty': 1,
            'order_id': sale_order.id,
            'price_unit': self.mollie_fees,
            'dr_fees_origin_id': self.id
        })
        return result
