# -*- coding: utf-8 -*-

import werkzeug
import logging

from odoo import http
from odoo.http import request, Response

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

            # Checked transaction state because webhook might have already confirmed the transection
            if transaction.exists() and transaction.acquirer_reference and transaction.state not in ['done', 'cancel']:
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

                if transaction.state in ['done', 'cancel']:

                    # We will process the payment from webhook confirmation. payment confirmation might
                    # be delayed and user might left the screen (may be user paid via QR and left the screen).
                    # A cron is already there for such confirmation but we will process the order immediately
                    # because we already got the confirmation and there is no need to wait for cron.
                    # /!\/!\/!\ Whenever you make changes here check `mollie_manual_payment_validation` method too.
                    if not transaction.is_processed and transaction.state == 'done':
                        transaction._post_process_after_done()

                    # We do not need next webhooks if payment is already done or canceled
                    return Response("OK", status=200)

        return Response("Not Confirmed", status=418)
