# -*- coding: utf-8 -*-

from odoo import fields, models


class POSMollieVoucher(models.Model):
    _name = 'pos.mollie.voucher'
    _description = 'Mollie voucher method'
    _rec_name = 'mollie_voucher_category'

    active = fields.Boolean(default=True)
    category_ids = fields.Many2many('product.category', string='Product Categories')
    product_ids = fields.Many2many('product.template', string='Products', domain="[('available_in_pos', '=', True)]")
    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('sport_culture', 'Sports & Culture'),
    ], required=True, copy=False)
