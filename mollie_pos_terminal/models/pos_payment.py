from odoo import models, fields, api


class PosPayment(models.Model):
    _inherit = "pos.payment"

    mollie_uid = fields.Char(string='Mollie UID', copy=False)
