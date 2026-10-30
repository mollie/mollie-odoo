# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    mollie_customer_id = fields.Char(string="Mollie Customer ID", readonly=True)
    mollie_is_oneoff_token = fields.Boolean(
        string="Requires Customer Approval", readonly=True,
        help="Saved card that the customer must approve on each payment. It cannot be charged automatically, e.g. for subscriptions.",
    )
