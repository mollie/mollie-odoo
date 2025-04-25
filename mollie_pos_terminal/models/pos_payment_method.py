import base64

from odoo import fields, models, api
from odoo.tools import file_open


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mollie_pos_terminal_id = fields.Many2one('mollie.pos.terminal', string='Mollie Pos Terminal', domain="[('status', '=', 'active')]")
    mollie_latest_response = fields.Json('History', default={})
    mollie_payment_default_partner = fields.Many2one('res.partner')
    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('sport_culture', 'Sports & Culture'),
    ], string='Voucher Category', copy=False)

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['mollie_payment_default_partner', 'mollie_voucher_category']
        return result

    def _get_payment_terminal_selection(self):
        return super(PosPaymentMethod, self)._get_payment_terminal_selection() + [('mollie', 'Mollie')]

    def mollie_payment_request(self, data):
        self.sudo().mollie_latest_response = {}  # avoid handling old responses multiple times
        if data.get('amount') >= 0:
            return self.mollie_pos_terminal_id._api_make_payment_request(data)
        elif data.get('mollie_origin_transaction_id'):
            return self.mollie_pos_terminal_id._api_make_refund_request(data)

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
