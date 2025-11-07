# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.exceptions import ValidationError
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.addons.payment_mollie.controllers.main import MollieController
from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class MolliePaymentPortal(PaymentPortal):

    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        if kwargs.get('provider_id'):
            provider_id = request.env['payment.provider'].sudo().browse(int(kwargs['provider_id']))
            if provider_id.code == 'mollie':
                if isinstance(additional_allowed_keys, tuple):
                    additional_allowed_keys += ('mollie_card_token', 'mollie_payment_issuer', 'mollie_save_card')
                if isinstance(additional_allowed_keys, set):
                    additional_allowed_keys.update(['mollie_card_token', 'mollie_payment_issuer', 'mollie_save_card'])
        super(MolliePaymentPortal, MolliePaymentPortal)._validate_transaction_kwargs(kwargs, additional_allowed_keys=additional_allowed_keys)

    def _create_transaction(
        self, provider_id, payment_method_id, token_id, amount, currency_id, partner_id, flow,
        tokenization_requested, landing_route, reference_prefix=None, is_validation=False,
        custom_create_values=None, **kwargs
    ):
        mollie_custom_create_values = {
            "mollie_card_token": kwargs.pop("mollie_card_token", None),
            "mollie_payment_issuer": kwargs.pop("mollie_payment_issuer", None),
            "mollie_save_card": kwargs.pop("mollie_save_card", None)
        }
        custom_create_values = custom_create_values or {}
        custom_create_values.update(mollie_custom_create_values)
        return super()._create_transaction(
            provider_id, payment_method_id, token_id, amount, currency_id, partner_id, flow,
            tokenization_requested, landing_route, reference_prefix=reference_prefix, is_validation=is_validation,
            custom_create_values=custom_create_values, **kwargs
        )

class MolliePayment(MollieController):

    @staticmethod
    def _verify_and_process(data):
        """Verify and process the payment data sent by Mollie.

        :param dict data: The payment data.
        :return: None
        """
        tx_sudo = request.env['payment.transaction'].sudo()._search_by_reference('mollie', data)
        if not tx_sudo:
            return

        try:
            # verified_data = tx_sudo._send_api_request(
            #     'GET', f'/payments/{tx_sudo.provider_reference}'
            # )
            verified_data = tx_sudo.provider_id._api_mollie_get_payment_data(tx_sudo.provider_reference, force_payment=True)
        except ValidationError:
            _logger.error("Unable to process the payment data")
        else:
            tx_sudo._process('mollie', verified_data)
