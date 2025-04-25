# -*- coding: utf-8 -*-

from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_pos_payment_method(self):
        result = super()._loader_params_pos_payment_method()
        result['search_params']['fields'].extend(['mollie_payment_default_partner', 'mollie_voucher_category'])
        return result

    def _create_split_account_payment(self, payment, amounts):
        payment_aml = super()._create_split_account_payment(payment, amounts)
        if payment and payment.payment_method_id.use_payment_terminal == 'mollie':
            for aml in payment_aml.move_id.line_ids:
                aml.name = aml.name + ' - ' + payment.pos_order_id.pos_reference
        return payment_aml

    def _loader_params_product_product(self):
        result = super()._loader_params_product_product()
        result["search_params"]["fields"].append("categ_id")
        return result

    def _get_pos_ui_product_product(self, params):
        result = super()._get_pos_ui_product_product(params)
        products_map, categ_map = {}, {}
        for voucher_line in self.env['pos.mollie.voucher'].search([]):
            for categ in voucher_line.category_ids:
                categ_map[categ.id] = voucher_line.mollie_voucher_category
            for product in voucher_line.product_ids:
                products_map[product.id] = voucher_line.mollie_voucher_category

        for product_data in result:
            product_categ_id = product_data.pop('categ_id')
            product_data['mollie_voucher_category'] = False
            if product_categ_id and categ_map.get(product_categ_id[0]):
                product_data['mollie_voucher_category'] = categ_map[product_categ_id[0]]
            if products_map.get(product_data['product_tmpl_id'][0]):
                product_data['mollie_voucher_category'] = products_map[product_data['product_tmpl_id'][0]]
        return result
