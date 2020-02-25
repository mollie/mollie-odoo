# -*- coding: utf-8 -*-
from odoo import models, fields, _
import pytz
import dateutil.parser
from odoo.addons.payment.models.payment_acquirer import ValidationError

import logging
import pprint
from mollie.api.client import Client
from .payment_acquirer_method import (
    get_base_url,
    get_mollie_provider_key,
)

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    _mollie_client = Client()
    _redirect_url = "/payment/mollie/redirect"

    acquirer_method = fields.Many2one(
        "payment.icon",
        string="Acquirer Method",
        domain="[('provider','=','mollie')]",
    )

    def _mollie_form_get_tx_from_data(self, data):
        reference = data.get("reference")
        payment_tx = self.search([("reference", "=", reference)])

        if not payment_tx or len(payment_tx) > 1:
            error_msg = _("received data for reference %s") % (
                pprint.pformat(reference)
            )
            if not payment_tx:
                error_msg += _("; no order found")
            else:
                error_msg += _("; multiple order found")
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        return payment_tx

    def _mollie_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        return invalid_parameters

    def _mollie_form_validate(self, data):
        reference = data.get("reference")
        acquirer = self.acquirer_id
        if self.state == "done":
            _logger.info(
                "Mollie: trying to validate an already validated tx (ref %s)",
                reference,
            )
            return True

        mollie_client = Client()
        tx = self._mollie_form_get_tx_from_data(data)
        transactionId = tx["acquirer_reference"]
        _logger.info(
            "Validated transfer payment forTx %s: set as pending" % (reference)
        )

        mollie_api_key = acquirer._get_mollie_api_keys(acquirer.state)[
            "mollie_api_key"
        ]
        mollie_client.set_api_key(mollie_api_key)
        mollie_response = mollie_client.payments.get(transactionId)
        try:
            # dateutil and pytz don't recognize abbreviations PDT/PST
            tzinfos = {"PST": -8 * 3600, "PDT": -7 * 3600}
            date = dateutil.parser.parse(
                data.get("createdAt"), tzinfos=tzinfos
            ).astimezone(pytz.utc)
        except Exception:
            date = fields.Datetime.now()
        res = {"acquirer_reference": mollie_response.get("id", "")}

        status = mollie_response.get("status", "undefined")

        if status in ["paid", "authorized"]:
            res.update(date=date)
            self._set_transaction_done()
            return self.write(res)

        elif status in ["canceled", "expired", "failed"]: # In the v1 API, canceled status was misspelled as cancelled [19430].
            self._set_transaction_cancel()
            return self.write(res)

        elif status in ["open", "pending"]:
            self._set_transaction_pending()
            return self.write(res)

        else:
            msg = "Error/%s/%s" % (transactionId, reference)
            self._set_transaction_error(msg)
            return self.write(res)

    def _get_mollie_order_line_data(self, order_lines):
        lines = []
        base_url = get_base_url(self.env)
        for line in order_lines:
            currency_name = (
                line.currency_id.name or line.move_id.currency_id.name
            )
            vatRate = 0.0
            tax_id = (
                line.tax_id
                if line._name == "sale.order.line"
                else line.tax_ids
            )
            for t in tax_id:
                if t.amount_type == "percent":
                    vatRate += t.amount
            # discountAmount = (
            #     line.price_unit_taxinc - line.price_reduce_taxinc
            # ) * int(line.product_uom_qty)
            quantity = (
                line.product_uom_qty
                if line._name == "sale.order.line"
                else line.quantity
            )
            line_data = {
                "type": "physical",
                "name": line.name,
                "quantity": int(quantity),
                "unitPrice": {
                    "currency": currency_name,
                    "value": "%.2f" % float(line.price_total / quantity),
                },
                # 'discountAmount': {
                #     "currency": line.currency_id.name,
                #     "value": '%.2f' % float(discountAmount)},
                "totalAmount": {
                    "currency": currency_name,
                    "value": "%.2f" % float(line.price_total),
                },
                "vatRate": "%.2f" % float(vatRate),
                "vatAmount": {
                    "currency": currency_name,
                    "value": "%.2f"
                    % float(line.price_total - line.price_subtotal),
                },
                "productUrl": "%s/line/%s" % (base_url, line.id),
            }
            lines.append(line_data)
        return lines

    def _get_mollie_order_data(self, order):
        orderNumber = "ODOO-%s" % (self.reference)
        order_lines = False
        if order._name == "account.move":
            order_lines = order.invoice_line_ids
        elif order._name == "sale.order":
            order_lines = order.order_line
        lines = self._get_mollie_order_line_data(order_lines)
        base_url = get_base_url(self.env)
        if not lines:
            message = _("_____No order lignes__")
            _logger.info(message)
            self.env["provider.log"]._post_log(
                {"name": message, "detail": message, "type": "olive"}
            )
            return False

        method = (
            self.acquirer_method and self.acquirer_method.acquirer_reference
        )
        billingAddress = order.partner_id._get_mollie_address()
        order_data = {
            "amount": {
                "value": "%.2f" % float(order.amount_total),
                "currency": order.currency_id.name,
            },
            "billingAddress": billingAddress,
            "metadata": {"order_id": orderNumber, "description": order.name},
            "locale": order.partner_id.lang or "nl_NL",
            "orderNumber": orderNumber,
            "redirectUrl": "%s%s?reference=%s"
            % (base_url, self._redirect_url, self.reference),
            "lines": lines,
        }
        if method:
            order_data.update({"method": method})
        return order_data

    def _set_lines_mollie_ref(self, order, response):
        if not response.get("lines", False):
            _logger.info("Error! There was no line found in the response.")
            return False

        for line in response["lines"]:
            if not line.get("_links", False):
                _logger.info("Error! No line links found.")
            if not line["_links"].get("productUrl", False):
                _logger.info("Error!_ No line links found in the productUrl.")

            productUrl_dic = line["_links"]["productUrl"]
            productUrl = productUrl_dic.get("href", "")
            splits = productUrl.split("/")
            line_id = int(splits[-1]) or False
            if not isinstance(line_id, int):
                _logger.info("Error! The lind_id is not an integer_")
                continue

            order_line = False
            if order._name == "invoice.move":
                order_line = order.invoice_line_ids.search(
                    [("move_id", "=", order.id), ("id", "=", line_id)]
                )
            elif order._name == "sale.order":
                order_line = order.order_line.search(
                    [("order_id", "=", order.id), ("id", "=", line_id)]
                )
            if order_line and len(order_line) == 1:
                order_line.acquirer_reference = line.get("id", "")
            else:
                _logger.info(
                    "Error! Multiple sale order lines with the same ID where found."
                )
                continue
        return True

    def mollie_orders_create(self):
        order = False
        if self.invoice_ids:
            order = self.invoice_ids[0]
        if not order and self.sale_order_ids:
            order = self.sale_order_ids[0]
        elif not order:
            return False
        payload = self._get_mollie_order_data(order)
        try:
            if not payload:
                message = _("No order data function mollie_orders_create")
                self.env["provider.log"]._post_log(
                    {"name": message, "detail": message, "type": "olive"}
                )
                return False
            response = self._mollie_client.orders.create(
                payload, embed="payments"
            )
            if response.get("status", "none") == "created":
                self.acquirer_reference = response.get("id", "")

            self._set_lines_mollie_ref(order, response)
            self.env["provider.log"]._post_log(
                {
                    "name": _("Order created"),
                    "detail": "%s" % (response,),
                    "type": "green",
                }
            )
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env["provider.log"]._post_log(
                {
                    "name": _("ERROR! on Create order"),
                    "detail": "%s\n %s" % (e, payload),
                    "type": "red",
                }
            )
            return False

    def mollie_orders_get(self):
        try:
            response = self._mollie_client.orders.get(
                self.acquirer_reference, embed="payments"
            )
            self.env["provider.log"]._post_log(
                {
                    "name": "Order exist",
                    "detail": "%s" % (response,),
                    "type": "green",
                }
            )
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env["provider.log"]._post_log(
                {"name": _("ERROR! on find order"), "detail": e, "type": "red"}
            )
            return False

    def mollie_orders_delete(self):
        try:
            response = self._mollie_client.orders.delete(
                self.acquirer_reference
            )
            self.env["provider.log"]._post_log(
                {
                    "name": "Order deleted",
                    "detail": "%s" % (response,),
                    "type": "green",
                }
            )
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env["provider.log"]._post_log(
                {
                    "name": _("ERROR! on delete order"),
                    "detail": e,
                    "type": "red",
                }
            )
            return False

    def mollie_order_sync(self, key=False):
        key = get_mollie_provider_key(self.env)
        try:
            self._mollie_client.set_api_key(key)
            response = False
            if not self.acquirer_reference:
                response = self.mollie_orders_create()
            else:
                response = self.mollie_orders_get()
                if not response:
                    response = self.mollie_orders_create()
                else:
                    self.mollie_orders_delete()
                    response = self.mollie_orders_create()
            return response
        except Exception as e:
            _logger.info("ERROR! %s" % (e,))
            self.env["provider.log"]._post_log(
                {"name": _("ERROR! on sync order"), "detail": e, "type": "red"}
            )
            return False
