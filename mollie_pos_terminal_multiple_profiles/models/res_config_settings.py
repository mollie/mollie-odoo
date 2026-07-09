from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_mollie_terminal_api_key = fields.Char(
        string="POS Mollie Terminal Api Key",
        related="pos_config_id.mollie_terminal_api_key",
        readonly=False,
    )
