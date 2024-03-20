# -*- coding: utf-8 -*-

from odoo.osv import expression
from odoo import fields, models


class MolliePaymentIssuers(models.Model):
    _name = 'mollie.payment.method.issuer'
    _description = 'Mollie payment method issuers'
    _order = "sequence, id"

    name = fields.Char(translate=True)
    sequence = fields.Integer()
    provider_id = fields.Many2one('mollie.payment.method', string='Provider')
    payment_icon_ids = fields.Many2many('payment.icon', string='Supported Payment Icons')
    issuers_code = fields.Char()
    active = fields.Boolean(default=True)


class MollieVoucherLines(models.Model):
    _name = 'mollie.voucher.line'
    _description = 'Mollie voucher method'

    method_id = fields.Many2one('payment.method', string='Mollie Method')
    category_ids = fields.Many2many('product.category', string='Product Categories')
    product_ids = fields.Many2many('product.template', string='Products')
    mollie_voucher_category = fields.Selection([('meal', 'Meal'), ('eco', 'Eco'), ('gift', 'Gift')], required=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_mollie_voucher_category(self):
        domain = [('product_ids', 'in', self.ids)]
        categories = self.mapped('categ_id')
        if categories:
            domain = expression.OR([domain, [('category_ids', 'parent_of', categories.ids)]])
        voucher_line = self.env['mollie.voucher.line'].search(domain, limit=1)
        return voucher_line and voucher_line.mollie_voucher_category or False
