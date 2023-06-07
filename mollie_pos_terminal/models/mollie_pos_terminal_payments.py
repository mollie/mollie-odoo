import logging
import requests
from werkzeug import urls

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MolliePosTerminal(models.Model):
    _name = 'mollie.pos.terminal.payments'
    _description = 'Mollie Pos Terminal'

    name = fields.Char("Transaction ID")
    mollie_uid = fields.Char("Mollie UID")
    terminal_id = fields.Many2one('mollie.pos.terminal')
    mollie_latest_response = fields.Json('Response', default={})
    status = fields.Selection([
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('canceled', 'Canceled'),
        ('pending', 'Pending'),
    ], default='open')

    def _create_mollie_payment_request(self, response, data):
        if response and response.get('status') == 'open':
            self.create({
                'name': response.get('id'),
                'mollie_uid': data.get('mollie_uid'),
                'terminal_id': data.get('terminal_id'),
                'mollie_latest_response': response,
                'status': response.get('status')
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

    def _mollie_process_webhook(self, webhook_data):
        mollie_payment = self.sudo().search([('name', '=', webhook_data.get('id'))], limit=1)
        if mollie_payment:
            payment_status = mollie_payment.terminal_id._api_get_mollie_payment_status(webhook_data.get('id'))
            if payment_status and payment_status.get('status'):
                mollie_payment.write({
                    'mollie_latest_response': payment_status,
                    'status': payment_status.get('status')
                })
