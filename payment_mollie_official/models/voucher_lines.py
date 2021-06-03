# -*- coding: utf-8 -*-

import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class MollieVoucherLines(models.Model):
    _name = 'mollie.voucher.line'

    def _default_voucher_category(self):
        """ We moved field from acquirer to method line.
            This will migrate existing lines to voucher method.
        """
        return self.env['mollie.payment.method'].with_context(active_test=False).search([('method_id_code', '=', 'voucher')], limit=1)

    method_id = fields.Many2one('mollie.payment.method', default=_default_voucher_category)
    category_id = fields.Many2one('product.category')
    mollie_voucher_category = fields.Selection(related="category_id.mollie_voucher_category", readonly=False)
    acquirer_id = fields.Many2one('payment.acquirer')

    def unlink(self):
        for voucher_line in self:
            voucher_line.mollie_voucher_category = False
        return super().unlink()
