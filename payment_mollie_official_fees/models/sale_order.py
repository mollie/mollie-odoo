# -*- coding: utf-8 -*-

from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    dr_fees_origin_id = fields.Many2one('payment.transaction', 'Mollie Fee Transaction')
