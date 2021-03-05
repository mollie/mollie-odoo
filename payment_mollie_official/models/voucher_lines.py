# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MollieVoucherLines(models.Model):
    _name = 'mollie.voucher.line'

    category_id = fields.Many2one('product.category')
    mollie_voucher_category = fields.Selection(related="category_id.mollie_voucher_category", readonly=False)
    acquirer_id = fields.Many2one('payment.acquirer')

    def unlink(self):
        for voucher_line in self:
            voucher_line.mollie_voucher_category = False
        return super().unlink()
