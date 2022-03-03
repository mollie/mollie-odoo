# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class MolliePaymentMethod(models.Model):
    _name = 'mollie.payment.method'
    _description = 'Mollie payment method'
    _order = "sequence, id"

    name = fields.Char(translate=True)
    sequence = fields.Integer()
    parent_id = fields.Many2one('payment.acquirer')  # This will be always mollie
    method_id_code = fields.Char(string="Method code")
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

    fees_active = fields.Boolean('Add Extra Fees')
    fees_dom_fixed = fields.Float('Fixed domestic fees')
    fees_dom_var = fields.Float('Variable domestic fees (in percents)')
    fees_int_fixed = fields.Float('Fixed international fees')
    fees_int_var = fields.Float('Variable international fees (in percents)')
    enable_qr_payment = fields.Boolean(string="Enable QR payment")

    mollie_voucher_ids = fields.One2many('mollie.voucher.line', 'method_id', string='Mollie Voucher Config')

    def _mollie_show_creditcard_option(self):
        if self.method_id_code != 'creditcard':
            return False
        acquirer_sudo = self.sudo().parent_id
        self.env.user._mollie_validate_customer_id(acquirer_sudo)
        if acquirer_sudo.mollie_profile_id and acquirer_sudo.sudo().mollie_use_components:
            return True
        if acquirer_sudo.sudo().mollie_show_save_card and not self.env.user.has_group('base.group_public'):
            return True
        return False
