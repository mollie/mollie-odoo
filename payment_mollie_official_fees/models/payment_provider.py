# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PaymentProviderMollie(models.Model):
    _inherit = 'payment.provider'

    mollie_fees_product_id = fields.Many2one('product.product', string='Mollie Fees Product')
