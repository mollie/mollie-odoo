# -*- coding: utf-8 -*-

import hashlib
import hmac

from odoo import models, api


class MolliePaymentLink(models.TransientModel):
    _inherit = "payment.link.wizard"

    def _custom_generate_link(self):
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        )
        self.link = (
            "%s/website_payment/pay?reference=%s&amount=%s&currency_id=%s&partner_id=%s&invoice_id=%s&access_token=%s"
            % (
                base_url,
                self.description,
                self.amount,
                self.currency_id.id,
                self.partner_id.id,
                self.res_id,
                self.access_token,
            )
        )

    @api.depends("amount", "description", "partner_id", "currency_id")
    def _compute_values(self):
        """ Override of the base method to add the invoice_id in the link. """
        secret = (
            self.env["ir.config_parameter"].sudo().get_param("database.secret")
        )
        for payment_link in self:
            token_str = "%s%s%s" % (
                payment_link.partner_id.id,
                payment_link.amount,
                payment_link.currency_id.id,
            )
            payment_link.access_token = hmac.new(
                secret.encode("utf-8"),
                token_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if payment_link.res_model == "account.move":
                payment_link._custom_generate_link()
            elif payment_link.res_model == "sale.order":
                payment_link._generate_link()
