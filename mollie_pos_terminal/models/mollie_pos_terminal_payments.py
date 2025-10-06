from odoo import fields, models, api


class MolliePosTerminal(models.Model):
    _name = 'mollie.pos.terminal.payments'
    _description = 'Mollie Pos Terminal'

    name = fields.Char("Transaction ID")
    mollie_uid = fields.Char("Mollie UID")
    terminal_id = fields.Many2one('mollie.pos.terminal')
    session_id = fields.Many2one('pos.session')
    mollie_latest_response = fields.Json('Response', default={})
    status = fields.Selection([
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('canceled', 'Canceled'),
        ('pending', 'Pending'),
    ], default='open')
    parent_payment_id = fields.Many2one("mollie.pos.terminal.payments", string='Origin payment')
    refund_payment_ids = fields.One2many("mollie.pos.terminal.payments", 'parent_payment_id', string='Refunds')

    def _create_mollie_payment_request(self, response, data):
        if response and response.get('status') in ['open', 'pending']:
            parent_payment_id = False
            if transaction_id := data.get('mollie_origin_transaction_id'):
                parent_payment_id = self.sudo().search([('name', '=', transaction_id)], limit=1)

            self.create({
                'name': response.get('id'),
                'mollie_uid': data.get('mollie_uid'),
                'terminal_id': data.get('terminal_id'),
                'session_id': data.get('session_id'),
                'mollie_latest_response': response,
                'status': response.get('status'),
                'parent_payment_id': parent_payment_id and parent_payment_id.id
            })

    @api.model
    def get_mollie_payment_status(self, transaction_id=None, mollie_uid=None):
        domain = []
        if transaction_id:
            domain.append(('name', '=', transaction_id))
        elif mollie_uid:
            domain.append(('mollie_uid', '=', mollie_uid))
        else:
            return {}
        mollie_payment = self.search(domain, limit=1)
        if mollie_payment:
            if mollie_payment.status in ['open', 'pending']:
                mollie_payment._mollie_process_webhook({'id': mollie_payment.name}, order_type='pos', notify=False)
            return mollie_payment.mollie_latest_response
        return {}

    @api.model
    def mollie_cancel_payment_request(self, transaction_id=None, mollie_uid=None):
        domain = []
        if transaction_id:
            domain.append(('name', '=', transaction_id))
        elif mollie_uid:
            domain.append(('mollie_uid', '=', mollie_uid))
        else:
            return {}
        mollie_payment = self.search(domain, limit=1)
        if mollie_payment and mollie_payment.status == 'open':
            return mollie_payment.terminal_id._api_cancel_mollie_payment(mollie_payment.name)
        return {}

    def _mollie_process_webhook(self, webhook_data, order_type='pos', notify=True):
        mollie_payment = self.sudo().search([('name', '=', webhook_data.get('id'))], limit=1)
        if mollie_payment:
            payment_status = mollie_payment.terminal_id._api_get_mollie_payment_status(webhook_data.get('id'))
            if payment_status and payment_status.get('status'):
                mollie_payment.write({
                    'mollie_latest_response': payment_status,
                    'status': payment_status.get('status')
                })

                if notify:
                    mollie_payment.session_id.config_id._notify("MOLLIE_TERMINAL_RESPONSE", mollie_payment.session_id.config_id.id)

                for refund_data in payment_status.get('_embedded', {}).get('refunds', []):
                    mollie_payment = self.sudo().search([('name', '=', refund_data.get('id'))], limit=1)
                    mollie_payment.write({
                        'mollie_latest_response': refund_data,
                        'status': refund_data.get('status')
                    })
