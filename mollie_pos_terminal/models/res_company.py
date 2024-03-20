from odoo import models, fields


class Company(models.Model):
    _inherit = 'res.company'

    mollie_terminal_api_key = fields.Char(string="Mollie Terminal Api Key")
