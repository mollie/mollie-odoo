import base64

from odoo import fields, models, api
from odoo.tools import file_open


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def get_mollie_payment_details(self, pos_session_id):
        mollie_line = self.payment_ids.filtered(lambda line: line.transaction_id and line.payment_method_id.use_payment_terminal == 'mollie')
        if len(mollie_line) == 1:
            mollie_payment_data = mollie_line.payment_method_id.mollie_pos_terminal_id._api_get_mollie_payment_status(mollie_line.transaction_id)
            if mollie_payment_data:
                return {
                    'amount_refunded': float(mollie_payment_data.get('amountRefunded', {}).get('value', '0')),
                    'amount_remaining': float(mollie_payment_data.get('amountRemaining', {}).get('value', '0')),
                }
        return False

    def get_mollie_transection_id(self, pos_session_id):
        # At the moment we only support refund for single transaction.
        # Will implement if needed
        mollie_lines = self.payment_ids.filtered(lambda line: line.transaction_id and line.payment_method_id.use_payment_terminal == 'mollie')
        return mollie_lines[0].transaction_id
