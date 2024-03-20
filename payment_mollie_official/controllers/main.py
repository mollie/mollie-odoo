# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.payment.controllers.portal import PaymentPortal


class MolliePaymentPortal(PaymentPortal):

    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        if kwargs.get('provider_id'):
            provider_id = request.env['payment.provider'].sudo().browse(int(kwargs['provider_id']))
            if provider_id.code == 'mollie':
                additional_allowed_keys += ('mollie_card_token', 'mollie_payment_issuer', 'mollie_save_card')
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
        return super()._create_transaction(provider_id, payment_method_id, token_id, amount, currency_id, partner_id, flow,
            tokenization_requested, landing_route, reference_prefix=reference_prefix, is_validation=is_validation,
            custom_create_values=custom_create_values, **kwargs
        )
