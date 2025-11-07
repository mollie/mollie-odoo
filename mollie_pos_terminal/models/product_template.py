# -*- coding: utf-8 -*-

from odoo import models, api, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # TODO: Need to remove the dummy field as its used for storing data on js side.
    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('sport_culture', 'Sports & Culture'),
    ], compute="_compute_mollie_voucher_category")

    def _compute_mollie_voucher_category(self):
        """
        This function computes the Mollie voucher category for products based on related voucher lines.
        """
        products_map, categ_map = {}, {}    
        for voucher_line in self.env['pos.mollie.voucher'].search([]):
            for categ in voucher_line.category_ids:
                categ_map[categ.id] = voucher_line.mollie_voucher_category
            for product in voucher_line.product_ids:
                products_map[product.id] = voucher_line.mollie_voucher_category
        for product_data in self:
            product_categ_id = product_data.categ_id
            if categ_map.get(product_categ_id.id):
                product_data.mollie_voucher_category = categ_map[product_categ_id.id]
            elif products_map.get(product_data.id):
                product_data.mollie_voucher_category = products_map[product_data.id]
            else:
                product_data.mollie_voucher_category = False

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_to_load = super()._load_pos_data_fields(config_id)
        fields_to_load += ['categ_id', 'mollie_voucher_category']
        return fields_to_load
