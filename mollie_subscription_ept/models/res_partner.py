import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    mollie_customer_id = fields.Char("Mollie Customer ID")
    mollie_subscription_ids = fields.One2many("mollie.subscription", "partner_id", "Subscriptions")
