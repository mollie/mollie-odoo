# -*- coding: utf-8 -*-

import pprint
import logging
import phonenumbers
from werkzeug import urls

from odoo.addons.payment_mollie_official import const
from odoo.addons.payment_mollie.controllers.main import MollieController
from odoo.exceptions import ValidationError, UserError

from odoo import _, api, fields, models, tools

_logger = logging.getLogger(__name__)

# Description size on Mollie side is 255
DESCRIPTION_SIZE = 255


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mollie_payment_issuer = fields.Char()
    mollie_card_token = fields.Char()
    mollie_reminder_payment_id = fields.Many2one('account.payment', string="Mollie Reminder Payment", readonly=True)
    mollie_origin_payment_reference = fields.Char()

    # Order Deprecated, will be removed in future
    mollie_payment_shipment_reference = fields.Char()

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on Mollie data.

        Note: self.ensure_one()

        :param dict notification_data: The feedback notification data sent by the provider
        :return: None
        """
        if self.provider_code != 'mollie':
            return super()._process_notification_data(notification_data)

        self._process_refund_transactions_status()

        if self.state == 'done':
            return

        provider_reference = self.provider_reference

        mollie_payment = self.provider_id._api_mollie_get_payment_data(provider_reference, force_payment=True)
        payment_status = mollie_payment.get('status')

        if mollie_payment.get('amountCaptured') and float(mollie_payment['amountCaptured']['value']) > 0.0:
            self._process_capture_transactions_status(mollie_payment['id'], payment_status)
            if payment_status != 'paid' or payment_status == 'paid' and self.state == 'done':
                return
        if payment_status == 'paid':
            self._set_done()
            if self.tokenize and not self.token_id:
                self._mollie_tokenize_from_notification_data(mollie_payment)
        elif payment_status == 'pending':
            self._set_pending()
        elif payment_status == 'authorized':
            self._set_authorized()
            if self.tokenize and not self.token_id:
                self._mollie_tokenize_from_notification_data(mollie_payment)
        elif payment_status in ['expired', 'canceled', 'failed']:
            self._set_canceled("Mollie: " + _("Mollie: canceled due to status: %s", payment_status))
        elif payment_status == 'open':
            self._set_error("Mollie: " + _("A payment was started, but not finished: %s", payment_status))
        else:
            _logger.info("Received data with invalid payment status: %s", payment_status)
            self._set_error("Mollie: " + _("Received data with invalid payment status: %s", payment_status))

    def _mollie_tokenize_from_notification_data(self, payment_data):
        """ Create a new token based on the notification data.

        Note: self.ensure_one()

        :param dict notification_data: The notification data sent by the provider
        :return: None
        """
        self.ensure_one()
        if 'customerId' not in payment_data or 'mandateId' not in payment_data:
            return

        token = self.env['payment.token'].create({
            'provider_id': self.provider_id.id,
            'payment_method_id': self.payment_method_id.id,
            'payment_details': payment_data.get('details', {}).get('cardNumber', False),
            'partner_id': self.partner_id.id,
            'provider_ref': payment_data.get('mandateId'),
            'mollie_customer_id': payment_data.get('customerId'),
        })
        self.write({
            'token_id': token,
            'tokenize': False,
        })
        _logger.info(
            "Created token with id %(token_id)s for partner with id %(partner_id)s from "
            "transaction with reference %(ref)s",
            {
                'token_id': token.id,
                'partner_id': self.partner_id.id,
                'ref': self.reference,
            },
        )

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Mollie-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific rendering values
        :rtype: dict
        """
        if self.provider_code != 'mollie':
            return super()._get_specific_rendering_values(processing_values)

        payment_data = self._mollie_create_payment_record()

        # if checkout links are not present means payment has been done via card token
        # and there is no need to checkout on mollie
        if payment_data.get("_links", {}).get("checkout"):
            mollie_checkout_url = payment_data["_links"]["checkout"]["href"]
            qr_src = payment_data.get('details', {}).get('qrCode', {}).get('src')
            return {'api_url': mollie_checkout_url, 'extra_params': urls.url_parse(mollie_checkout_url).decode_query(), 'qr_src': qr_src}
        else:
            return {
                'api_url': payment_data.get('redirectUrl'),
                'ref': self.reference
            }

    def _send_payment_request(self):
        """Override of `payment` to send a payment request to Mollie."""
        if self.provider_code != 'mollie':
            return super()._send_payment_request()

        # Prepare the payment request to Mollie.
        if not self.token_id:
            raise UserError("Mollie: " + _("The transaction is not linked to a token."))

        # Send the payment request to Mollie.
        payment_data = self._mollie_create_payment_record()
        if not payment_data:  # The payment data might be missing if Mollie failed to create it.
            return  # There is nothing to process; the transaction is in error at this point.

        self._handle_notification_data('mollie', payment_data)

    def _send_refund_request(self, amount_to_refund=None):
        """ Override of payment to send a refund request to Authorize.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund
        :param bool create_refund_transaction: Whether a refund transaction should be created or not
        :return: The refund transaction if any
        :rtype: recordset of `payment.transaction`
        """
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'mollie':
            return refund_tx

        provider_reference = self.provider_reference
        if self.provider_reference.startswith('cpt_'):
            provider_reference = self.source_transaction_id.provider_reference
        payment_data = self.provider_id._api_mollie_get_payment_data(provider_reference, force_payment=True)
        refund_data = self.provider_id._api_mollie_refund(amount_to_refund, self.currency_id.name, payment_data.get('id'))
        refund_tx.provider_reference = refund_data.get('id')
        refund_tx.source_transaction_id._handle_notification_data('mollie', payment_data)
        if self.env.context.get('dr_refund_wizard'):
            refund_wizard = self.env['payment.refund.wizard'].sudo().browse(self.env.context.get('dr_refund_wizard'))
            refund_wizard.payment_id.mollie_refund_reference = refund_tx.id
        return refund_tx

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'mollie' or len(tx) == 1:
            return tx
        if notification_data.get('id'):
            tx = self.search(
                [('provider_reference', '=', notification_data.get('id')), ('provider_code', '=', 'mollie')]
            )
            if not tx:
                raise ValidationError("Mollie: " + _(
                    "No transaction found matching provider reference %s.", notification_data.get('id')
                ))
        return tx

    def _send_capture_request(self, amount_to_capture=None):
        """ Override of `payment` to send a capture request to Mollie. """
        child_capture_tx = super()._send_capture_request(amount_to_capture=amount_to_capture)
        if self.provider_code != 'mollie':
            return child_capture_tx

        # Make the capture request to Mollie
        capture_values = {
            'amount': {
                'currency': self.currency_id.name,
                'value': "%.2f" % amount_to_capture
            },
        }
        if self.amount != amount_to_capture and self.payment_method_code not in const.MULTI_CAPTURE_METHODS:
            # For payment methods that require full amount capture only, raise error for partial captures
            raise UserError(_('%s does not support partial captures. Please capture the full amount.'%(self.payment_method_id.name)))
        payment_data = self.provider_id._api_mollie_sync_capture(self.provider_reference, capture_values)
        _logger.info(
            "capture request response for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payment_data)
        )
        if child_capture_tx:
            child_capture_tx.provider_reference = payment_data.get('id')

        return child_capture_tx

    def _send_void_request(self, amount_to_void=None):
        """ transaction to void the payment
        cancel remaining quantity
        check context mollie_amount: to check amount_to_void was calculated with mollie or not
        :param float amount_to_void: The amount to be voided.
        :return: The created void child transaction, if any.
        :rtype: payment.transaction
        """
        child_void_tx = super()._send_void_request(amount_to_void=amount_to_void)
        if self.provider_code != 'mollie':
            return child_void_tx
        payment_data = self.provider_id._api_mollie_void_remaining_payment(self.provider_reference)
        _logger.info(
            "void request response for transaction with reference %s:\n%s",
            self.reference, pprint.pformat(payment_data)
        )
        if child_void_tx and payment_data:
            child_void_tx._set_canceled()
        return child_void_tx

    def _create_child_transaction(self, amount, is_refund=False, **custom_create_values):
        """ Inherit this method to create a refund transaction linked to the source payment transaction
            when the refund is processed from a captured transaction. """
        if self.provider_id.code == 'mollie' and is_refund and self.provider_reference.startswith('cpt_'):
            return self.source_transaction_id._create_child_transaction(amount, is_refund, **custom_create_values)
        return super()._create_child_transaction(amount, is_refund, **custom_create_values)

    def _create_payment(self, **extra_create_values):
        """ Overridden method to create reminder payment for vouchers."""
        if self.provider_id._get_code() == 'mollie':
            mollie_method = self.payment_method_id
            if mollie_method and mollie_method.journal_id:
                mollie_method_payment_code = mollie_method._get_journal_method_code()
                payment_method_line = mollie_method.journal_id.inbound_payment_method_line_ids.filtered(lambda l: l.code == mollie_method_payment_code)
                extra_create_values['journal_id'] = mollie_method.journal_id.id
                extra_create_values['payment_method_line_id'] = payment_method_line.id

            # handle special cases for vouchers
            if mollie_method.code == 'voucher':

                # We need to get payment information because transaction with "voucher" method
                # might paid with multiple payment method. So we need to payment data to check
                # how payment is done.
                mollie_payment = self.provider_id._api_mollie_get_payment_data(self.provider_reference)
                # When payment is done via order API
                if mollie_payment.get('resource') == 'order' and mollie_payment.get('_embedded'):
                    payment_list = mollie_payment['_embedded'].get('payments', [])
                    if len(payment_list):
                        mollie_payment = payment_list[0]
                remainder_method_code = mollie_payment['details'].get('remainderMethod')
                if remainder_method_code:  # if there is remainder amount
                    primary_journal = mollie_method.journal_id or self.provider_id.journal_id
                    for odoo_method_code, mollie_method_code in const.PAYMENT_METHODS_MAPPING.items():
                        if mollie_method_code == remainder_method_code:
                            remainder_method_code = odoo_method_code
                    remainder_method = self.provider_id.payment_method_ids.filtered(lambda m: m.code == remainder_method_code)
                    remainder_journal = remainder_method.journal_id or self.provider_id.journal_id

                    reminder_mollie_method_payment_code = remainder_method._get_journal_method_code()
                    remainder_payment_method_line = remainder_method.journal_id.inbound_payment_method_line_ids.filtered(lambda pm_line: pm_line.code == reminder_mollie_method_payment_code)

                    # if both journals are diffrent then we need to split the payment
                    if primary_journal != remainder_journal:
                        voucher_amount = sum([float(voucher['amount']['value']) for voucher in mollie_payment['details']['vouchers']])
                        voucher_amount = tools.float_round(voucher_amount, precision_digits=2)
                        extra_create_values['amount'] = abs(voucher_amount)

                        # Create remainder payment record
                        remainder_create_values = {
                            **extra_create_values,
                            'amount': float(mollie_payment['details']['remainderAmount']['value']),  # A tx may have a negative amount, but a payment must >= 0
                            'payment_type': 'inbound' if self.amount > 0 else 'outbound',
                            'currency_id': self.currency_id.id,
                            'partner_id': self.partner_id.commercial_partner_id.id,
                            'partner_type': 'customer',
                            'journal_id': remainder_journal.id,
                            'company_id': self.provider_id.company_id.id,
                            'payment_method_line_id': remainder_payment_method_line.id,
                            'payment_token_id': self.token_id.id,
                            'payment_transaction_id': self.id,
                            'memo': self.reference,
                        }

                        remainder_payment = self.env['account.payment'].create(remainder_create_values)
                        remainder_payment.action_post()
                        self.mollie_reminder_payment_id = remainder_payment

        payment_record = super()._create_payment(**extra_create_values)

        # Post the reminder payment if auto invoice is activated (if invoice is presents)
        if self.invoice_ids and self.mollie_reminder_payment_id:
            (self.invoice_ids.line_ids + self.mollie_reminder_payment_id.line_ids).filtered(
                lambda line: line.account_id == self.mollie_reminder_payment_id.destination_account_id and not line.reconciled
            ).reconcile()

        return payment_record

    def _get_received_message(self):
        """ Overridden method to add reminder payment data."""
        self.ensure_one()

        message = super()._get_received_message()
        if message and self.state == 'done' and self.mollie_reminder_payment_id:
            message += _(
                "\nThe payment remaining amount is posted: %s",
                self.mollie_reminder_payment_id._get_html_link()
            )
        return message

    def _mollie_create_payment_record(self, silent_errors=False):
        """ This method payment/order record in mollie based on api type.

        :param str api_type: api is selected based on this parameter
        :return: data of created record received from mollie api
        :rtype: dict
        """
        self.ensure_one()
        payment_data, params = self._mollie_prepare_payment_payload()
        result = self.provider_id._api_mollie_create_payment_record(payment_data, params=params, silent_errors=silent_errors)

        # We are setting provider reference as we are receiving it before 3DS payment
        # So we can verify the validity of the transecion
        if result and result.get('id'):
            self.provider_reference = result.get('id')
        return result

    def _mollie_prepare_payment_payload(self):
        """ This method prepare the payload based in api type.

        Note: this method are splitted so we can write test cases

        :param str api_type: api is selected based on this parameter
        :return: data of created record received from mollie api
        :rtype: dict
        """
        base_url = self.provider_id.get_base_url()
        redirect_url = urls.url_join(base_url, MollieController._return_url)
        params = {}
        payment_data = {
            'method': const.PAYMENT_METHODS_MAPPING.get(
                self.payment_method_code, self.payment_method_code
            ),
            'amount': {
                'currency': self.currency_id.name,
                'value': "%.2f" % self.amount
            },
            'metadata': {
                'transaction_id': self.id,
                'reference': self.reference,
            },
            'locale': self.provider_id._mollie_user_locale(),
            'redirectUrl': f'{redirect_url}?ref={self.reference}'
        }
        provider = self.provider_id

        if provider.capture_manually and payment_data.get('method') in const.CAPTURE_METHODS:
            payment_data['captureMode'] = 'manual'

        payment_data.update({
            'description': self.reference,
        })

        if self.invoice_ids:
            invoice = self.invoice_ids[0]
            invoice_total = invoice.amount_total
            lines = []
            if self.amount == invoice_total:
                lines = self._mollie_get_invoice_lines(invoice)

            payment_data.update({
                'lines': lines
            })

        if self.sale_order_ids:
            order = self.sale_order_ids[0]
            order_total = order.amount_total
            lines = []

            if self.amount == order_total:
                lines = self._mollie_get_order_lines(order)

            payment_data.update({
                'lines': lines,
            })
        else:
            # Payment api parameters
            payment_data['description'] = self.reference

        if (self.invoice_ids or self.sale_order_ids) and self.payment_method_code in const.BILLING_ADDRESS_REQUIRED_METHODS:
            payment_data['billingAddress'] = self._prepare_mollie_address()

        # Mollie rejects some local ips/URLs
        # https://help.mollie.com/hc/en-us/articles/213470409
        webhook_url = urls.url_join(base_url, MollieController._webhook_url)
        if "://localhost" not in webhook_url and "://192.168." not in webhook_url and "://127." not in webhook_url:
            payment_data['webhookUrl'] = f'{webhook_url}?ref={self.reference}'

        method_specific_parameters = {}
        # Add if transaction has cardToken
        if self.mollie_card_token:
            method_specific_parameters['cardToken'] = self.mollie_card_token

        if self.tokenize and not self.env.user.has_group('base.group_public') and self.payment_method_code in const.MANDATE_METHODS:
            mollie_customer_id = self.provider_id._mollie_get_customer_id(self.partner_id)
            if mollie_customer_id:
                method_specific_parameters.update({
                    "customerId": mollie_customer_id,
                    "sequenceType": "first",
                })
                if payment_data.get('captureMode') == 'manual':
                    del payment_data['captureMode']

        # Add if transaction has issuer
        if self.mollie_payment_issuer:
            method_specific_parameters['issuer'] = self.mollie_payment_issuer

        payment_data.update(method_specific_parameters)
        if self.token_id:
            payment_data.update({
                "customerId": self.token_id.mollie_customer_id,
                "mandateId": self.token_id.provider_ref,
                "sequenceType": "recurring",
            })
            payment_data.pop("method")

        method_record = self.provider_id.payment_method_ids.filtered(lambda m: m.code == self.payment_method_id.code)
        if method_record.mollie_enable_qr_payment:
            params['include'] = 'details.qrCode'
        return payment_data, params

    def _mollie_get_order_lines(self, order):
        """ This method prepares order line data for order api

        :param order: sale.order record based on this payload will be genrated
        :return: order line data for order api
        :rtype: dict
        """
        lines = []
        lines_amount_total = 0.0
        for line in order.order_line.filtered(lambda l: not l.display_type):  # ignore notes and section lines
            if line.price_total == 0:
                continue
            line_type = 'physical'
            is_negative_line = line.price_total < 0
            quantity = int(abs(line.product_uom_qty))
            unit_price = abs(line.price_reduce_taxinc)
            if not line.product_uom_qty.is_integer():
                quantity = 1  # Mollie does not support float quantities.
                unit_price = abs(line.price_total)
            if is_negative_line:
                line_type = 'discount'
                unit_price = -abs(unit_price)
            lines_amount_total += line.price_total
            line_data = {
                'description': line.name[:DESCRIPTION_SIZE],
                'type': line_type,
                'quantity': quantity,
                'unitPrice': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % unit_price,
                },
                'totalAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_total,
                },
            }
            if line.product_id.type == 'service' and line_type != 'discount':
                line_data['type'] = 'digital'  # We are considering service product as digital as we don't do shipping for it.

            if 'is_delivery' in line._fields and line.is_delivery and line_type != 'discount':
                line_data['type'] = 'shipping_fee'

            if line.product_id and 'website_url' in line.product_id._fields:
                base_url = self.get_base_url()
                line_data['productUrl'] = urls.url_join(base_url, line.product_id.website_url)

            if self.payment_method_id.code == 'voucher':
                category = line.product_id.product_tmpl_id._get_mollie_voucher_category()
                if category:
                    line_data.update({
                        'categories': category
                    })
            lines.append(line_data)
        if self.provider_id.mollie_rounding_adjustment:
            self._prepare_rounding_adjustment_line(order, lines, lines_amount_total)
        return lines

    def _mollie_get_invoice_lines(self, invoice):
        """
        Format invoice lines for Mollie's order API.

        :param invoice: account.move record
        :return: List of dicts representing Mollie-compatible invoice lines
        """
        lines = []
        lines_amount_total = 0.00
        for line in invoice.invoice_line_ids.filtered(lambda l: l.display_type not in ['line_section', 'line_note']):
            if line.price_total == 0:
                continue
            line_type = 'physical'
            is_negative_line = line.price_total < 0
            quantity = int(abs(line.quantity)) or 1
            unit_price = abs(line.price_total / quantity)
            if not line.quantity.is_integer():
                quantity = 1  # Mollie does not support float quantities.
                unit_price = abs(line.price_total)
            if is_negative_line:
                line_type = 'discount'
                unit_price = -abs(unit_price)
            lines_amount_total += line.price_total

            line_data = {
                'description': line.name[:DESCRIPTION_SIZE],
                'type': line_type,
                'quantity': quantity,
                'quantityUnit': line.product_uom_id.name or 'pcs',
                'unitPrice': {
                    'currency': line.currency_id.name,
                    'value': f"{unit_price:.2f}",
                },
                'totalAmount': {
                    'currency': line.currency_id.name,
                    'value': f"{line.price_total:.2f}",
                }
            }

            if line.product_id and 'website_url' in line.product_id._fields:
                base_url = self.get_base_url()
                line_data['productUrl'] = urls.url_join(base_url, line.product_id.website_url)

            lines.append(line_data)
        if self.provider_id.mollie_rounding_adjustment:
            self._prepare_rounding_adjustment_line(invoice, lines, lines_amount_total)
        return lines

    def _prepare_rounding_adjustment_line(self, record, lines, lines_amount_total):
        lines_amount_total = record.currency_id.round(lines_amount_total)
        rounding_difference = record.currency_id.round(self.amount - lines_amount_total)
        if rounding_difference != 0:
            rounding_line_type = 'digital' if rounding_difference > 0 else 'discount'
            line_data = {
                'description': self.provider_id.rounding_line_description or _("Rounding Adjustment"),
                'type': rounding_line_type,
                'quantity': 1,
                'unitPrice': {
                    'currency': record.currency_id.name,
                    'value': "%.2f" % rounding_difference,
                },
                'totalAmount': {
                    'currency': record.currency_id.name,
                    'value': "%.2f" % rounding_difference,
                },
            }
            lines.append(line_data)

    def _prepare_mollie_address(self):
        """ This method prepare address used in order api of mollie

        :return: address data for order api
        :rtype: dict
        """
        self.ensure_one()
        result = {}
        partner = self.partner_id
        if not partner:
            return result

        # organizationName is required for billie
        if self.payment_method_code == 'billie':
            if not partner.commercial_company_name:
                raise ValidationError(_('Company name is necessary for Billie payments. Go to address and add company name.'))
            result['organizationName'] = partner.commercial_company_name

        # Build the name becasue 'givenName' and 'familyName' is required.
        # So we will repeat the name is one is not present
        name_parts = partner.name.split(" ")
        result['givenName'] = name_parts[0]
        result['familyName'] = ' '.join(name_parts[1:]) if len(name_parts) > 1 else result['givenName']

        # Phone
        phone = self._mollie_phone_format(self.partner_phone)
        if phone:
            result['phone'] = phone
        result['email'] = self.partner_email

        # Address
        result["streetAndNumber"] = self.partner_address or ' '
        result["postalCode"] = self.partner_zip or ' '
        result["city"] = self.partner_city or ' '
        result["country"] = self.partner_country_id and self.partner_country_id.code or ' '
        return result

    @api.model
    def _mollie_phone_format(self, phone):
        """ Mollie only allows E164 phone numbers so this method checks whether its validity."""
        if phone:
            try:
                parse_phone = phonenumbers.parse(phone, None)
                if parse_phone:
                    phone = phonenumbers.format_number(
                        parse_phone, phonenumbers.PhoneNumberFormat.E164
                    )
            except Exception:
                _logger.warning("Can not format customer phone number for mollie")
        return phone

    def _process_refund_transactions_status(self):
        self.ensure_one()
        refund_transactions = self.sudo().search([('source_transaction_id', 'in', self.ids), ('operation', '=', 'refund'), ('state', 'in', ['pending', 'draft'])])
        for transection in refund_transactions:
            if transection.provider_reference:
                source_reference = transection.source_transaction_id.provider_reference

                # Order API deprecated remove code to manage 'ord_' references
                if source_reference.startswith('ord_'):
                    payment_data = self.provider_id._api_mollie_get_payment_data(source_reference, force_payment=True)
                    source_reference = payment_data.get('id')

                refund_data = transection.provider_id._api_mollie_refund_data(source_reference, transection.provider_reference)
                if refund_data and refund_data.get('id'):
                    if refund_data.get('status') == 'refunded':
                        transection._set_done()
                    elif refund_data.get('status') in ['pending', 'queued', 'processing']:
                        transection._set_pending()
                    elif refund_data.get('status') == 'failed':
                        self._set_canceled("Mollie: " + _("Mollie: failed due to status: %s", refund_data.get('status')))

    def _process_capture_transactions_status(self, payment_reference, payment_status):
        capture_data = self.provider_id._api_mollie_get_capture_data(payment_reference)
        if not capture_data.get('count'):
            return

        for capture in capture_data['_embedded']['captures']:
            capture_id = capture.get('id')
            capture_status = capture.get('status')
            capture_amount = capture['amount']['value']
            payment_id = capture.get('paymentId')
            shipment_id = capture.get('shipmentId')

            # Find existing transaction for this capture
            capture_tx = self.child_transaction_ids.filtered(lambda tx: tx.provider_reference == capture_id)

            # Create a new child transaction if not found
            if not capture_tx:
                capture_tx = self._create_child_transaction(
                    capture_amount,
                    provider_reference=capture_id,
                    mollie_origin_payment_reference=payment_id,
                    mollie_payment_shipment_reference=shipment_id
                )

            # Update transaction status if needed
            if capture_tx:
                current_state = capture_tx.state
                if capture_status == 'succeeded' and current_state != 'done':
                    capture_tx._set_done()
                elif capture_status == 'failed' and current_state != 'cancel':
                    capture_tx._set_canceled()
                elif capture_status == 'pending' and current_state != 'pending':
                    capture_tx._set_pending()

        if payment_status == 'paid' and self.payment_method_code not in const.MULTI_CAPTURE_METHODS:
            # Calculate amounts for different transaction states
            transaction_total_amount = self.amount
            confirmed_amount = sum(
                self.child_transaction_ids.filtered(lambda tx: tx.state == 'done').mapped('amount')
            )
            cancelled_amount = sum(
                self.child_transaction_ids.filtered(lambda tx: tx.state == 'cancel').mapped('amount')
            )

            # Calculate remaining amount that needs to be cancelled
            remaining_amount_to_cancel = transaction_total_amount - confirmed_amount - cancelled_amount

            # Cancel the remaining amount if any
            if self.currency_id.compare_amounts(remaining_amount_to_cancel, 0) > 0:
                void_transaction = self._create_child_transaction(remaining_amount_to_cancel)
                void_transaction._log_sent_message()
                void_transaction._set_canceled()
