import json
import logging
import psycopg2
import requests
from werkzeug import urls

from odoo import fields, models, _, api, SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)


class MolliePosTerminal(models.Model):
    _name = 'mollie.pos.terminal'
    _description = 'Mollie Pos Terminal'

    name = fields.Char()
    terminal_id = fields.Char('Terminal ID')
    profile_id = fields.Char('Profile ID')
    serial_number = fields.Char('Serial Number')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ])
    currency_id = fields.Many2one('res.currency', string='Currency')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    mollie_debug_logging = fields.Boolean('Debug logging', help="Log requests in order to ease debugging")

    def toggle_mollie_debug(self):
        for provider in self:
            provider.mollie_debug_logging = not provider.mollie_debug_logging

    def _log_logging(self, env, message, function_name, path, provider_id):
        if self.mollie_debug_logging:
            self.env.flush_all()
            db_name = self._cr.dbname
            try:
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    IrLogging = env['ir.logging']
                    IrLogging.sudo().create({
                        'name': 'Mollie Terminal',
                        'type': 'server',
                        'level': 'DEBUG',
                        'dbname': db_name,
                        'message': message or 'N/A',
                        'func': function_name or 'N/A',
                        'path': path,
                        'line': provider_id,
                    })
            except psycopg2.Error:
                pass

    def _sync_mollie_terminals(self):
        existing_terminals = self.search([])
        terminals_data = self._api_get_terminals()  # TODO: manage pager for 250+ terminals

        if not terminals_data.get('count'):
            return

        for terminal in terminals_data['_embedded']['terminals']:
            terminal_found = existing_terminals.filtered(lambda x: x.terminal_id == terminal['id'])
            currency = self.env['res.currency'].search([('name', '=', terminal['currency'])])

            if not currency:
                raise ValidationError(_('Currency ') + terminal['currency'] + _(' is not active. Please activate it first.'))

            terminal_data = {
                'name': terminal['description'],
                'terminal_id': terminal['id'],
                'profile_id': terminal['profileId'],
                'serial_number': terminal['serialNumber'],
                'status': terminal['status'],
                'currency_id': currency.id
            }
            if terminal_found:
                terminal_found.write(terminal_data)
            else:
                self.create(terminal_data)

    # =================
    # API CALLS METHODS
    # =================

    def _api_get_terminals(self):
        """ Fetch terminals data from mollie api """
        return self._mollie_api_call('/terminals', method='GET')

    def _api_make_payment_request(self, data):
        payment_payload = self._prepare_payment_payload(data)
        result = self._mollie_api_call('/payments', data=payment_payload, method='POST', silent=True)
        self.env['mollie.pos.terminal.payments']._create_mollie_payment_request(result, {**data, 'terminal_id': self.id})
        return result

    def _api_make_refund_request(self, data):
        refund_payload, mollie_origin_transaction_id = self._prepare_refund_payload(data)
        result = self._mollie_api_call(f'/payments/{mollie_origin_transaction_id}/refunds', data=refund_payload, method='POST', silent=True)
        self.env['mollie.pos.terminal.payments']._create_mollie_payment_request(result, {**data, 'terminal_id': self.id})
        return result

    def _api_cancel_mollie_payment(self, transaction_id):
        return self.sudo()._mollie_api_call(f'/payments/{transaction_id}', method='DELETE', silent=True)

    def _api_get_mollie_payment_status(self, transaction_id):
        return self.sudo()._mollie_api_call(f'/payments/{transaction_id}?embed=refunds', method='GET', silent=True)

    def _prepare_payment_payload(self, data):
        base_url = self.get_base_url()
        order_type = data.get('order_type', 'pos')
        webhook_url = urls.url_join(base_url, f"/pos_mollie/webhook/{order_type}")
        result = {
            "amount": {
                "currency": data['curruncy'],
                "value": f"{data['amount']:.2f}"
            },
            "description": f"{data['description']} Voucher Payment" if data.get('mollie_voucher_category') else data['description'],
            "webhookUrl": webhook_url,
            "redirectUrl": webhook_url,
            "method": "pointofsale",
            "terminalId": self.terminal_id,
            "metadata": {
                "mollie_uid": data['mollie_uid'],
                "order_id": data['order_id'],
                "payment_method_id": data['payment_method_id'],
                'order_type': order_type
            }
        }
        if data.get('mollie_voucher_category'):
            result.update({
                "lines": [
                {
                    "description": "Voucher payment",
                    "quantity": 1,
                    "unitPrice": {
                        "currency": data['curruncy'],
                        "value": f"{data['amount']:.2f}"
                    },
                    "totalAmount": {
                        "currency": data['curruncy'],
                        "value": f"{data['amount']:.2f}"
                    },
                    "categories": [
                        data.get('mollie_voucher_category')
                    ]
                }
                ],
            })
        return result

    def _prepare_refund_payload(self, data):
        return {
            "amount": {
                "currency": data['curruncy'],
                "value": f"{abs(data['amount']):.2f}"
            },
            "metadata": {
                "mollie_uid": data['mollie_uid'],
                "order_id": data['order_id'],
                "payment_method_id": data['payment_method_id'],
                'order_type': 'pos'
            }
        }, data['mollie_origin_transaction_id']

    def action_sync_terminals(self):
        return {
            "name": _("Sync Terminal"),
            "type": "ir.actions.act_window",
            "res_model": "sync.mollie.terminal",
            "target": "new",
            "views": [[False, "form"]],
            "context": {"is_modal": True},
        }

    # =====================
    # GENERIC TOOLS METHODS
    # =====================

    def _mollie_api_call(self, endpoint, data=None, method='POST', silent=False):
        company = self.company_id or self.env.company

        headers = {
            'content-type': 'application/json',
            "Authorization": f'Bearer {company.mollie_terminal_api_key}',
        }

        endpoint = f'/v2/{endpoint.strip("/")}'
        url = urls.url_join('https://api.mollie.com/', endpoint)

        _logger.info('Mollie POS Terminal CALL on: %s', url)

        try:
            response = requests.request(method, url, json=data, headers=headers, timeout=60)
            if response.status_code == 204:
                result = True  # returned no content
            else:
                result = response.json()
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            error_details = response.json()
            _logger.exception("MOLLIE-POS-ERROR \n %s", error_details)
            if silent:
                result = error_details
            else:
                raise ValidationError("MOLLIE: \n %s" % error_details)
        except requests.exceptions.RequestException as e:
            _logger.exception("unable to communicate with Mollie: %s \n %s", url, e)
            if silent:
                result = {'error': "Some thing went wrong"}
            else:
                raise ValidationError("Mollie: " + _("Some thing went wrong."))
        finally:
            if self.mollie_debug_logging:
                message = str(json.dumps({
                    'DATA': data,
                    'RESPONSE': result
                }, indent=4))
                self._log_logging(self.env, message, method, url, self.id)
        return result

    def show_form_and_tree(self):
        action = self.env['ir.actions.actions']._for_xml_id('mollie_pos_terminal.mollie_pos_terminal_payments_action')
        action.update({
            'domain': [('terminal_id', '=', self.id)],
            'views': [(self.env.ref('mollie_pos_terminal.mollie_pos_terminal_payments_view_tree').id, 'list'), (self.env.ref('mollie_pos_terminal.mollie_pos_terminal_payments_view_form').id, 'form')],
            'res_id': self.id,
        })
        return action
