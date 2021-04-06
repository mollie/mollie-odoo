# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MolliePaymentMethod(models.Model):
    _name = 'mollie.payment.method'
    _description = 'Mollie payment method'
    _order = "sequence, id"

    name = fields.Char()
    sequence = fields.Integer()
    parent_id = fields.Many2one('payment.acquirer')  # This will be always mollie
    method_id_code = fields.Char()
    payment_icon_ids = fields.Many2many('payment.icon', string='Supported Payment Icons')
    active = fields.Boolean(default=True)
    active_on_shop = fields.Boolean(string="Enabled on shop", default=True)
    journal_id = fields.Many2one(
        'account.journal', 'Payment Journal', domain="[('type', 'in', ['bank', 'cash'])]",
        help="""Journal where the successful transactions will be posted""")
    min_amount = fields.Float()
    max_amount = fields.Float()

    supports_order_api = fields.Boolean(string="Supports Order API")
    supports_payment_api = fields.Boolean(string="Supports Payment API")

    payment_issuer_ids = fields.Many2many('mollie.payment.method.issuer', string='Issuers')

    country_ids = fields.Many2many('res.country', string='Country Availability')
