# -*- coding: utf-8 -*-

import werkzeug
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MollieController(http.Controller):
    _notify_url = "/payment/mollie/notify"
    _redirect_url = "/payment/mollie/redirect"

    @http.route("/payment/mollie/action", type='http', auth="public", methods=['POST'], csrf=False, sitemap=False)
    def mollie_redirect(self, **post):
        if post.get('checkout_url'):
            return werkzeug.utils.redirect(post.get('checkout_url'))
        return werkzeug.utils.redirect("/payment/process")

    @http.route("/payment/mollie/redirect", type='http', auth="public", csrf=False, sitemap=False)
    def mollie_return(self, **post):
        if post.get('tx'):
            transaction = request.env["payment.transaction"].sudo().browse(int(post.get('tx')))
            if transaction.exists() and transaction.acquirer_reference:
                data = transaction.acquirer_id._mollie_get_payment_data(transaction.acquirer_reference)
                request.env["payment.transaction"].sudo().form_feedback(data, "mollie")
        return werkzeug.utils.redirect("/payment/process")

    @http.route("/payment/mollie/notify", type='http', auth="public", methods=['POST'], csrf=False, sitemap=False)
    def mollie_notify(self, **post):
        if post.get('tx'):
            transaction = request.env["payment.transaction"].sudo().browse(int(post.get('tx')))
            if transaction.exists() and transaction.acquirer_reference == post.get('id'):
                data = transaction.acquirer_id._mollie_get_payment_data(transaction.acquirer_reference)
                request.env["payment.transaction"].sudo().form_feedback(data, "mollie")
        return "ok"
