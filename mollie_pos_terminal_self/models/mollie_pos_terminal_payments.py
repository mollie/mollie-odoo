
from odoo import models, fields


class MolliePosTerminal(models.Model):
    _inherit = 'mollie.pos.terminal.payments'
    _description = 'Mollie Pos Terminal'

    def _mollie_process_webhook(self, webhook_data, order_type, notify=True):
        if order_type != 'kiosk':
            return super()._mollie_process_webhook(webhook_data, order_type, notify)

        mollie_payment = self.sudo().search([('name', '=', webhook_data.get('id'))], limit=1)
        if mollie_payment:
            payment_status = mollie_payment.terminal_id._api_get_mollie_payment_status(webhook_data.get('id'))
            if payment_status and payment_status.get('status'):
                mollie_payment.write({
                    'mollie_latest_response': payment_status,
                    'status': payment_status.get('status')
                })
                order_reference = payment_status.get('description')
                payment_method_id = payment_status['metadata'].get('payment_method_id')
                order_sudo = self.env['pos.order'].sudo().search([('pos_reference', '=', order_reference)], limit=1)

                order = order_sudo.sudo(False).with_user(order_sudo.session_id.config_id.self_ordering_default_user_id).with_company(order_sudo.session_id.config_id.company_id)

                if payment_status['status'] == 'paid':
                    payment_amount = float(payment_status['amount']['value'])
                    order.add_payment({
                        'amount': payment_amount,
                        'payment_date': fields.Datetime.now(),
                        'payment_method_id': payment_method_id,
                        'transaction_id': payment_status['id'],
                        'payment_status': payment_status.get('status'),
                        'pos_order_id': order.id
                    })
                    order._action_set_partner(payment_method_id)
                    order.action_pos_order_paid()
                    order._send_order()
                if order.config_id.self_ordering_mode == 'kiosk':
                    order.config_id._notify('PAYMENT_STATUS', {
                        'payment_result': payment_status['status'] == 'paid' and 'Success' or payment_status['status'],
                        'data': {
                            'pos.order': order.read(order._load_pos_self_data_fields(order.config_id.id), load=False),
                            'pos.order.line': order.lines.read(order._load_pos_self_data_fields(order.config_id.id), load=False),
                        }
                    })
