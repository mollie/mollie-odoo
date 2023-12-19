import base64

from odoo import fields, models, api
from odoo.tools import file_open


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mollie_pos_terminal_id = fields.Many2one('mollie.pos.terminal', string='Mollie Pos Terminal', domain="[('status', '=', 'active')]")
    mollie_latest_response = fields.Json('History', default={})
    mollie_payment_default_partner = fields.Many2one('res.partner')

    def _get_payment_terminal_selection(self):
        return super(PosPaymentMethod, self)._get_payment_terminal_selection() + [('mollie', 'Mollie')]

    def mollie_payment_request(self, data):
        self.sudo().mollie_latest_response = {}  # avoid handling old responses multiple times
        return self.mollie_pos_terminal_id._api_make_payment_request(data)

    def _is_write_forbidden(self, fields):
        whitelisted_fields = {'mollie_latest_response'}
        return super(PosPaymentMethod, self)._is_write_forbidden(fields - whitelisted_fields)

    @api.model_create_multi
    def create(self, vals_list):
        for val in vals_list:
            if not val.get('image') and val.get('use_payment_terminal') == 'mollie':
                mollie_image = file_open('mollie_pos_terminal/static/src/img/mollie-icon.png', mode='rb').read()
                if mollie_image:
                    val['image'] = base64.b64encode(mollie_image)
        return super().create(vals_list)
