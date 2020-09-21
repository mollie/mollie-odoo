# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MolliePaymentIssuers(models.Model):
    _name = 'mollie.payment.method.issuer'
    _description = 'Mollie payment method issuers'
    _order = "sequence, id"

    name = fields.Char()
    sequence = fields.Integer()
    parent_id = fields.Many2one('mollie.payment.method')
    payment_icon_ids = fields.Many2many('payment.icon', string='Supported Payment Icons')
    issuers_id_code = fields.Char()
    active = fields.Boolean(default=True)
