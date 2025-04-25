# -*- coding: utf-8 -*-

from odoo import models, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_to_load = super()._load_pos_data_fields(config_id)
        return fields_to_load + ["categ_id"]

    def _load_pos_data(self, data):
        result = super()._load_pos_data(data)
        products_map, categ_map = {}, {}
        for voucher_line in self.env['pos.mollie.voucher'].search([]):
            for categ in voucher_line.category_ids:
                categ_map[categ.id] = voucher_line.mollie_voucher_category
            for product in voucher_line.product_ids:
                products_map[product.id] = voucher_line.mollie_voucher_category

        for product_data in result['data']:
            product_categ_id = product_data.pop('categ_id')
            if categ_map.get(product_categ_id):
                product_data['mollie_voucher_category'] = categ_map[product_categ_id]
            if products_map.get(product_data['product_tmpl_id']):
                product_data['mollie_voucher_category'] = products_map[product_data['product_tmpl_id']]
        result['fields'].append('mollie_voucher_category')
        return result
