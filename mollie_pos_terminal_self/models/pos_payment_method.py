from odoo import models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _payment_request_from_kiosk(self, order):
        if self.use_payment_terminal != 'mollie':
            return super().payment_request_from_kiosk(order)
        else:
            payment_data = {
                'description': order.pos_reference,
                'curruncy': order.currency_id.name,
                'amount': order.amount_total,
                'session_id': order.session_id.id,
                'order_id': order.id,
                'mollie_uid': f'pos_order_{order.id}',
                'payment_method_id': self.id,
                'order_type': 'kiosk'
            }
            result = self.mollie_payment_request(payment_data)
            return result and result.get('status') == 'open'

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _action_set_partner(self, payment_method_id):
        payment_method = self.env['pos.payment.method'].sudo().browse(payment_method_id)
        if payment_method.use_payment_terminal == 'mollie' and payment_method.split_transactions and payment_method.mollie_payment_default_partner:
            self.sudo().write({'partner_id': payment_method.mollie_payment_default_partner.id})
        return True