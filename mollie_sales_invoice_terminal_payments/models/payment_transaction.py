# -*- coding: utf-8 -*-

from odoo import models, fields
from werkzeug import urls

from odoo.addons.payment.const import CURRENCY_MINOR_UNITS
from odoo.addons.payment_mollie import const
from odoo.addons.payment_mollie.controllers.main import MollieController


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    terminal_id = fields.Many2one('mollie.payments.terminal')

    def _mollie_terminal_api_make_payment_request(self):
        payload = self._mollie_terminal_prepare_payment_payload()
        payment_data = self.provider_id._mollie_make_request('/payments', data=payload)

        self.provider_reference = payment_data.get('id')
        return payment_data

    def _mollie_terminal_prepare_payment_payload(self):
        base_url = self.provider_id.get_base_url()
        webhook_url = urls.url_join(base_url, MollieController._webhook_url)
        decimal_places = CURRENCY_MINOR_UNITS.get(
            self.currency_id.name, self.currency_id.decimal_places
        )
        metadata = {'transaction_id': self.id}

        if self.sale_order_ids:
            metadata['order_id'] = self.sale_order_ids.ids
        elif self.invoice_ids:
            metadata['invoice_id'] = self.invoice_ids.ids

        return {
            'description': self.reference,
            'amount': {
                'currency': self.currency_id.name,
                'value': f"{self.amount:.{decimal_places}f}",
            },
            'method': [const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_code, self.payment_method_code
            )],
            'terminalId': self.terminal_id.terminal_id,
            'webhookUrl': f'{webhook_url}?ref={self.reference}',
            'metadata': metadata,
        }

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)

        # We post process immediately for terminal payments
        if self.provider_code != 'mollie' or not self.terminal_id or self.payment_method_code != 'pointofsale':
            return
        self.filtered(lambda tx: tx.state == 'done')._post_process()
