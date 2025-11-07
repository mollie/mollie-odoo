# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieVoucherLines(models.Model):
    _name = 'mollie.voucher.line'
    _description = 'Mollie voucher method'

    method_id = fields.Many2one('payment.method', string='Mollie Method')
    category_ids = fields.Many2many('product.category', string='Product Categories')
    product_ids = fields.Many2many('product.template', string='Products')
    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('consume', 'Consommation'),
        ('sports', 'Sports & Culture'),
        ('additional', 'Compliments')
    ], required=True)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_mollie_voucher_category(self):
        voucher_lines = self.env['mollie.voucher.line'].search([('product_ids', 'in', self.ids)])
        categories = (self - voucher_lines.product_ids).mapped('categ_id')
        if categories:
            category_voucher_lines = self.env['mollie.voucher.line'].search([('category_ids', 'in', categories.ids)])
            voucher_lines |= category_voucher_lines
        return voucher_lines and voucher_lines.mapped('mollie_voucher_category') or False
