from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mollie_pos_terminal_id = fields.Many2one('mollie.pos.terminal', string='Mollie Pos Terminal', domain="[('status', '=', 'active')]")

    def _get_payment_terminal_selection(self):
        return super(PosPaymentMethod, self)._get_payment_terminal_selection() + [('mollie', 'Mollie')]

    def mollie_payment_request(self, data):
        return self.mollie_pos_terminal_id._api_make_payment_request(data)
