# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request

class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    fees_active = fields.Boolean(string="Add Extra Fees")
    fees_dom_fixed = fields.Float(string="Fixed domestic fees")
    fees_dom_var = fields.Float(string="Variable domestic fees (in percents)")
    fees_int_fixed = fields.Float(string="Fixed international fees")
    fees_int_var = fields.Float(string="Variable international fees (in percents)")

    def _compute_fees(self, amount, country, provider, order_id=None):
        """ This method compute fees for the mollie method configuration.

        :param float amount: amount for fees
        :param recordset country: The customer country, as a `res.country` record
        :param recordset provider: The provider of the transaction, as a `payment.provider` record
        :return: fees for the mollie method
        :rtype: float
        """
        self.ensure_one()
        fees = 0.0
        if self.fees_active:
            if country == provider.company_id.country_id:
                fixed = self.fees_dom_fixed
                variable = self.fees_dom_var
            else:
                fixed = self.fees_int_fixed
                variable = self.fees_int_var
            fees = (amount * variable / 100.0 + fixed)
            if not order_id:
                return fees
            # Round before building the line, so that the fees added to the transaction amount are
            # computed on the very same price unit as the line created once the payment is done.
            fees = order_id.currency_id.round(fees)
            line_id = self.env['sale.order.line'].new({
                'product_id': provider.mollie_fees_product_id.id,
                'product_uom_qty': 1,
                'order_id': order_id.id,
                'price_unit': fees,
            })
            price_total = line_id.price_total
            tax_ids = line_id.tax_ids
            # Tax-included price: total amount is considered both subtotal and total.
            if len(tax_ids) == 1 and tax_ids.price_include_override == 'tax_included':
                return price_total, price_total
            return line_id.price_subtotal, price_total

    def _get_compatible_payment_methods(
        self, provider_ids, partner_id, currency_id=None, force_tokenization=False,
        is_express_checkout=False, report=None, **kwargs
    ):

        result_pms = super()._get_compatible_payment_methods(
            provider_ids, partner_id, currency_id=currency_id, force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout, report=report, **kwargs
        )
        if not provider_ids:
            return result_pms

        def is_mollie_method(method):
            return method.provider_ids.filtered(lambda p: p.id in provider_ids)[:1]._get_code() == 'mollie'

        if not kwargs.get('sale_order_id') and request and request.params.get('invoice_id'):
            fees_pms = result_pms.filtered(lambda pm: pm.fees_active and is_mollie_method(pm))
            return result_pms - fees_pms
        return result_pms
