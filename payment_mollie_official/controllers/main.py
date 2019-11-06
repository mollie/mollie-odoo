# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging
from mollie.api.client import Client
import phonenumbers
import werkzeug

from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import WebsitePayment, PaymentProcessing

_logger = logging.getLogger(__name__)


class MollieController(http.Controller):
    _notify_url = '/payment/mollie/notify'
    _redirect_url = '/payment/mollie/redirect'
    _cancel_url = '/payment/mollie/cancel'
    _mollie_client = Client()

    @http.route([
        '/payment/mollie/notify'],
        type='http', auth='none', methods=['GET'])
    def mollie_notify(self, **post):
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect('/payment/process')

    @http.route([
        '/payment/mollie/redirect'], type='http', auth="none", methods=['GET'])
    def mollie_redirect(self, **post):
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect('/payment/process')

    @http.route([
        '/payment/mollie/cancel'], type='http', auth="none", methods=['GET'])
    def mollie_cancel(self, **post):
        request.env['payment.transaction'].sudo().form_feedback(post, 'mollie')
        return werkzeug.utils.redirect('/payment/process')

    @http.route(['/payment/mollie/intermediate'], type='http',
                auth="none", methods=['POST'], csrf=False)
    def mollie_intermediate(self, **post):
        base_url = post['BaseUrl']
        tx_reference = post['Description']

        payment_tx = request.env['payment.transaction'].sudo()._mollie_form_get_tx_from_data({
            'reference': tx_reference
        })
        if post.get("Method", False):
            payment_tx.update({"acquirer_method": int(post.get("Method", False))})

        webhook_url = '%s/web#id=%s&action=%s&model=%s&view_type=form' % (
            base_url, payment_tx.id,
            'payment.action_payment_transaction', 'payment.transaction')

        self._mollie_client.set_api_key(post['Key'])
        order_response = payment_tx.mollie_order_sync()
        if order_response and order_response["status"] == "created":
            if '_embedded' in order_response:
                embedded = order_response['_embedded']
                if 'payments' in embedded:
                    payment = embedded['payments'][-1]
                    payment_tx.write({"acquirer_reference": payment["id"]})

            checkout_url = order_response["_links"]["checkout"]["href"]
            return werkzeug.utils.redirect(checkout_url)
        return werkzeug.utils.redirect("/")


class CustomWebsitePayment(WebsitePayment):

    # Override for the set mollie payment method
    @http.route(['/website_payment/transaction/<string:reference>/<string:amount>/<string:currency_id>',
                '/website_payment/transaction/v2/<string:amount>/<string:currency_id>/<path:reference>',
                '/website_payment/transaction/v2/<string:amount>/<string:currency_id>/<path:reference>/<int:partner_id>'], type='json', auth='public')
    def transaction(self, acquirer_id, reference, amount, currency_id, partner_id=False, **kwargs):
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        order_id = kwargs.get('order_id')

        reference_values = order_id and {'sale_order_ids': [(4, order_id)]} or {}
        reference = request.env['payment.transaction']._compute_reference(values=reference_values, prefix=reference)

        values = {
            'acquirer_id': int(acquirer_id),
            'reference': reference,
            'amount': float(amount),
            'currency_id': int(currency_id),
            'partner_id': partner_id,
            'type': 'form_save' if acquirer.save_token != 'none' and partner_id else 'form',
        }

        if order_id:
            values['sale_order_ids'] = [(6, 0, [order_id])]

        reference_values = order_id and {'sale_order_ids': [(4, order_id)]} or {}
        reference_values.update(acquirer_id=int(acquirer_id))
        values['reference'] = request.env['payment.transaction']._compute_reference(values=reference_values, prefix=reference)
        tx = request.env['payment.transaction'].sudo().with_context(lang=None).create(values)
        tx = request.env['payment.transaction'].sudo().browse(tx.id)
        secret = request.env['ir.config_parameter'].sudo().get_param('database.secret')
        token_str = '%s%s%s' % (tx.id, tx.reference, round(tx.amount, tx.currency_id.decimal_places))
        token = hmac.new(secret.encode('utf-8'), token_str.encode('utf-8'), hashlib.sha256).hexdigest()
        tx.return_url = '/website_payment/confirm?tx_id=%d&access_token=%s' % (tx.id, token)

        PaymentProcessing.add_payment_transaction(tx)
        # BizzAppDev Customization Start
        render_values = {
            'partner_id': partner_id,
            'Method': kwargs.get("Method", False)
        }
        # BizzAppDev Customization End
        return acquirer.sudo().render(tx.reference, float(amount), int(currency_id), values=render_values)
