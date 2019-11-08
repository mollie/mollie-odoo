# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging
from unicodedata import normalize
from mollie.api.client import Client
import werkzeug

from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import (
    WebsitePayment,
    PaymentProcessing,
)

_logger = logging.getLogger(__name__)


class MollieController(http.Controller):
    _notify_url = "/payment/mollie/notify"
    _redirect_url = "/payment/mollie/redirect"
    _cancel_url = "/payment/mollie/cancel"
    _mollie_client = Client()

    @http.route(
        ["/payment/mollie/notify"], type="http", auth="none", methods=["GET"]
    )
    def mollie_notify(self, **post):
        request.env["payment.transaction"].sudo().form_feedback(post, "mollie")
        return werkzeug.utils.redirect("/payment/process")

    @http.route(
        ["/payment/mollie/redirect"], type="http", auth="none", methods=["GET"]
    )
    def mollie_redirect(self, **post):
        request.env["payment.transaction"].sudo().form_feedback(post, "mollie")
        return werkzeug.utils.redirect("/payment/process")

    @http.route(
        ["/payment/mollie/cancel"], type="http", auth="none", methods=["GET"]
    )
    def mollie_cancel(self, **post):
        request.env["payment.transaction"].sudo().form_feedback(post, "mollie")
        return werkzeug.utils.redirect("/payment/process")

    @http.route(
        ["/payment/mollie/intermediate"],
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def mollie_intermediate(self, **post):
        tx_reference = post["Description"]

        payment_tx = (
            request.env["payment.transaction"]
            .sudo()
            ._mollie_form_get_tx_from_data({"reference": tx_reference})
        )
        if post.get("Method", False):
            payment_tx.update(
                {"acquirer_method": int(post.get("Method", False))}
            )

        self._mollie_client.set_api_key(post["Key"])
        order_response = payment_tx.mollie_order_sync()
        if order_response and order_response["status"] == "created":
            if "_embedded" in order_response:
                embedded = order_response["_embedded"]
                if "payments" in embedded:
                    payment = embedded["payments"][-1]
                    payment_tx.write({"acquirer_reference": payment["id"]})

            checkout_url = order_response["_links"]["checkout"]["href"]
            return werkzeug.utils.redirect(checkout_url)
        return werkzeug.utils.redirect("/")


class CustomWebsitePayment(WebsitePayment):

    # Override function for the set invoice_id
    @http.route(
        ["/website_payment/pay"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def pay(
        self,
        reference="",
        order_id=None,
        amount=False,
        currency_id=None,
        acquirer_id=None,
        partner_id=False,
        access_token=None,
        **kw
    ):
        env = request.env
        user = env.user.sudo()
        reference = (
            normalize("NFKD", reference)
            .encode("ascii", "ignore")
            .decode("utf-8")
        )
        if partner_id and not access_token:
            raise werkzeug.exceptions.NotFound
        if partner_id and access_token:
            token_ok = request.env["payment.link.wizard"].check_token(
                access_token, int(partner_id), float(amount), int(currency_id)
            )
            if not token_ok:
                raise werkzeug.exceptions.NotFound

        # Default values
        values = {"amount": 0.0, "currency": user.company_id.currency_id}

        # Check sale order
        if order_id:
            try:
                order_id = int(order_id)
                order = env["sale.order"].browse(order_id)
                values.update(
                    {
                        "currency": order.currency_id,
                        "amount": order.amount_total,
                        "order_id": order_id,
                    }
                )
            except Exception:
                order_id = None

        # Check currency
        if currency_id:
            try:
                currency_id = int(currency_id)
                values["currency"] = env["res.currency"].browse(currency_id)
            except Exception:
                pass

        # Check amount
        if amount:
            try:
                amount = float(amount)
                values["amount"] = amount
            except Exception:
                pass

        # Check reference
        reference_values = (
            order_id and {"sale_order_ids": [(4, order_id)]} or {}
        )
        values["reference"] = env["payment.transaction"]._compute_reference(
            values=reference_values, prefix=reference
        )

        # Check acquirer
        acquirers = None
        if acquirer_id:
            acquirers = env["payment.acquirer"].browse(int(acquirer_id))
        if not acquirers:
            acquirers = env["payment.acquirer"].search(
                [
                    ("state", "in", ["enabled", "test"]),
                    ("company_id", "=", user.company_id.id),
                ]
            )

        # Check partner
        if not user._is_public():
            # NOTE: this means that if the partner was set in the GET param,
            # it gets overwritten here
            # This is something we want, since security rules are based on the
            # partner - assuming the access_token checked out at the start,
            # this should have no impact on the payment itself
            # existing besides making reconciliation possibly more difficult
            # (if the payment partner is not the same as the invoice partner,
            # for example)
            partner_id = user.partner_id.id
        elif partner_id:
            partner_id = int(partner_id)

        values.update(
            {
                "partner_id": partner_id,
                "bootstrap_formatting": True,
                "error_msg": kw.get("error_msg"),
            }
        )

        # s2s mode will always generate a token, which we don't want for
        # public users
        valid_flows = ["form", "s2s"] if not user._is_public() else ["form"]
        values["acquirers"] = [
            acq for acq in acquirers if acq.payment_flow in valid_flows
        ]
        values["pms"] = request.env["payment.token"].search(
            [("acquirer_id", "in", acquirers.ids)]
        )
        # BizzAppDev Customization Start
        if kw.get("invoice_id", False):
            values.update({"invoice_id": kw["invoice_id"]})
        # BizzAppDev Customization Start
        return request.render("payment.pay", values)

    # Override for the set invoice_id in payment transaction
    @http.route(
        [
            "/website_payment/transaction/<string:reference>/<string:amount>/<string:currency_id>",
            "/website_payment/transaction/v2/<string:amount>/<string:currency_id>/<path:reference>",
            "/website_payment/transaction/v2/<string:amount>/<string:currency_id>/<path:reference>/<int:partner_id>",
        ],
        type="json",
        auth="public",
    )
    def transaction(
        self,
        acquirer_id,
        reference,
        amount,
        currency_id,
        partner_id=False,
        **kwargs
    ):
        acquirer = request.env["payment.acquirer"].browse(acquirer_id)
        order_id = kwargs.get("order_id")
        # BizzAppDev Customization Start
        invoice_id = kwargs.get("invoice_id")
        # BizzAppDev Customization End

        reference_values = (
            order_id and {"sale_order_ids": [(4, order_id)]} or {}
        )
        # BizzAppDev Customization Start
        if invoice_id:
            reference_values.update({"invoice_ids": [(4, int(invoice_id))]})
        # BizzAppDev Customization End

        reference = request.env["payment.transaction"]._compute_reference(
            values=reference_values, prefix=reference
        )

        values = {
            "acquirer_id": int(acquirer_id),
            "reference": reference,
            "amount": float(amount),
            "currency_id": int(currency_id),
            "partner_id": partner_id,
            "type": "form_save"
            if acquirer.save_token != "none" and partner_id
            else "form",
        }

        if order_id:
            values["sale_order_ids"] = [(6, 0, [order_id])]
        # BizzAppDev Customization Start
        if invoice_id:
            values["invoice_ids"] = [(6, 0, [invoice_id])]
        # BizzAppDev Customization End
        reference_values = (
            order_id and {"sale_order_ids": [(4, order_id)]} or {}
        )
        if invoice_id:
            reference_values.update({"invoice_ids": [(4, int(invoice_id))]})
        reference_values.update(acquirer_id=int(acquirer_id))
        values["reference"] = request.env[
            "payment.transaction"
        ]._compute_reference(values=reference_values, prefix=reference)
        tx = (
            request.env["payment.transaction"]
            .sudo()
            .with_context(lang=None)
            .create(values)
        )
        tx = request.env["payment.transaction"].sudo().browse(tx.id)
        secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("database.secret")
        )
        token_str = "%s%s%s" % (
            tx.id,
            tx.reference,
            round(tx.amount, tx.currency_id.decimal_places),
        )
        token = hmac.new(
            secret.encode("utf-8"), token_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        tx.return_url = "/website_payment/confirm?tx_id=%d&access_token=%s" % (
            tx.id,
            token,
        )

        PaymentProcessing.add_payment_transaction(tx)
        render_values = {
            "partner_id": partner_id,
        }
        return acquirer.sudo().render(
            tx.reference, float(amount), int(currency_id), values=render_values
        )
