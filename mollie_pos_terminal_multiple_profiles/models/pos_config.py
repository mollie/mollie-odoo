from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    mollie_terminal_api_key = fields.Char()
