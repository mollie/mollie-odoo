# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mollie_voucher_category = fields.Selection([('meal', 'Meal'), ('eco', 'Eco'), ('gift', 'Gift')])

    def _get_mollie_voucher_category(self):
        self.ensure_one()
        if self.mollie_voucher_category:
            return self.mollie_voucher_category
        mollie_voucher_category = False
        category_id = self.categ_id
        if category_id:
            while not mollie_voucher_category and category_id:
                mollie_voucher_category = category_id.mollie_voucher_category
                category_id = category_id.parent_id
        return mollie_voucher_category


class ProductCategory(models.Model):
    _inherit = 'product.category'

    mollie_voucher_category = fields.Selection([('meal', 'Meal'), ('eco', 'Eco'), ('gift', 'Gift')])
