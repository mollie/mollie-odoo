
# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Deprecated field, will be removed in upcoming version
    mollie_customer_id = fields.Char()
