# -*- coding: utf-8 -*-

import logging
import phonenumbers
from werkzeug import urls

from odoo.http import request
from odoo.addons.payment_mollie.controllers.main import MollieController
from odoo.exceptions import ValidationError

from odoo import _, api, fields, models, tools

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mollie_payment_method = fields.Char()
    mollie_payment_issuer = fields.Char()
    mollie_card_token = fields.Char()
    mollie_save_card = fields.Boolean()
    mollie_reminder_payment_id = fields.Many2one('account.payment', string="Mollie Reminder Payment", readonly=True)

    @api.model_create_multi
    def create(self, values_list):
        """ Add the custom fees to the transaction based on mollie methods. """
        transactions = super().create(values_list)

        for transaction in transactions:
            if transaction.provider_code == 'mollie' and transaction.mollie_payment_method:
                mollie_method = transaction.provider_id.mollie_methods_ids.filtered(lambda method: method.method_code == transaction.mollie_payment_method)
                if mollie_method and mollie_method.fees_active:
                    transaction.fees = mollie_method._compute_fees(
                        transaction.amount, transaction.currency_id, transaction.partner_id.country_id
                    )
        transactions.invalidate_cache(['amount', 'fees'])
        return transactions

    def _process_notification_data(self, data):
        """ Override of payment to process the transaction based on Mollie data.

        Note: self.ensure_one()

        :param dict data: The feedback data sent by the provider
        :return: None
        """
        if self.provider_code != 'mollie':
            return super()._process_notification_data(data)

        self._process_refund_transactions_status()

        if self.state == 'done':
            return

        provider_reference = self.provider_reference
        mollie_payment = self.provider_id._api_mollie_get_payment_data(provider_reference)
        payment_status = mollie_payment.get('status')
        if payment_status == 'paid':
            if mollie_payment.get('amountCaptured') and float(mollie_payment['amountCaptured']['value']) < self.amount:
                self.amount = mollie_payment['amountCaptured']['value']
            self._set_done()
        elif payment_status == 'pending':
            self._set_pending()
        elif payment_status == 'authorized':
            self._set_authorized()
        elif payment_status in ['expired', 'canceled', 'failed']:
            self._set_canceled("Mollie: " + _("Mollie: canceled due to status: %s", payment_status))
        elif payment_status == 'open':
            self._set_error("Mollie: " + _("A payment was started, but not finished: %s", payment_status))
        else:
            _logger.info("Received data with invalid payment status: %s", payment_status)
            self._set_error("Mollie: " + _("Received data with invalid payment status: %s", payment_status))

    @api.model
    def _get_specific_create_values(self, provider, values):
        """ Complete the values of the `create` method with provider-specific values.

        For an provider to add its own create values, it must overwrite this method and return a
        dict of values. provider-specific values take precedence over those of the dict of generic
        create values.

        :param str provider: The provider of the provider that handled the transaction
        :param dict values: The original create values
        :return: The dict of provider-specific create values
        :rtype: dict
        """

        if provider != 'mollie':
            return super()._get_specific_create_values(provider, values)

        create_values = {}
        if request and request.params.get('mollie_card_token'):
            create_values['mollie_card_token'] = request.params.get('mollie_card_token')
        if request and request.params.get('mollie_method'):
            create_values['mollie_payment_method'] = request.params.get('mollie_method')
        if request and request.params.get('mollie_issuer'):
            create_values['mollie_payment_issuer'] = request.params.get('mollie_issuer')
        if request and request.params.get('mollie_save_card'):
            create_values['mollie_save_card'] = request.params.get('mollie_save_card')

        return create_values

    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Mollie-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of provider-specific rendering values
        :rtype: dict
        """
        if self.provider_code != 'mollie':
            return super()._get_specific_rendering_values(processing_values)

        payment_data = self._create_mollie_order_or_payment()

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

    def _send_refund_request(self, amount_to_refund=None, create_refund_transaction=True):
        """ Override of payment to send a refund request to Authorize.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund
        :param bool create_refund_transaction: Whether a refund transaction should be created or not
        :return: The refund transaction if any
        :rtype: recordset of `payment.transaction`
        """
        if self.provider_code != 'mollie':
            return super()._send_refund_request(
                amount_to_refund=amount_to_refund,
                create_refund_transaction=create_refund_transaction,
            )

        refund_tx = super()._send_refund_request(
            amount_to_refund=amount_to_refund, create_refund_transaction=True
        )
        payment_data = self.provider_id._api_mollie_get_payment_data(self.provider_reference, force_payment=True)
        refund_data = self.provider_id._api_mollie_refund(amount_to_refund, self.currency_id.name, payment_data.get('id'))
        refund_tx.provider_reference = refund_data.get('id')
        refund_tx.fees = 0.0

        return refund_tx

    def _create_payment(self, **extra_create_values):
        """ Overridden method to create reminder payment for vouchers."""
        if self.mollie_payment_method:
            mollie_method = self.provider_id.mollie_methods_ids.filtered(lambda method: method.method_code == self.mollie_payment_method)
            if mollie_method and mollie_method.journal_id:
                mollie_method_payment_code = mollie_method._get_journal_method_code()
                payment_method_line = mollie_method.journal_id.inbound_payment_method_line_ids.filtered(lambda l: l.code == mollie_method_payment_code)
                extra_create_values['journal_id'] = mollie_method.journal_id.id
                extra_create_values['payment_method_line_id'] = payment_method_line.id

            # handle special cases for vouchers
            if mollie_method.method_code == 'voucher':

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
                    remainder_method = self.provider_id.mollie_methods_ids.filtered(lambda m: m.method_code == remainder_method_code)
                    remainder_journal = remainder_method.journal_id or self.provider_id.journal_id

                    reminder_mollie_method_payment_code = remainder_method._get_journal_method_code()
                    remainder_payment_method_line = remainder_method.journal_id.inbound_payment_method_line_ids.filtered(lambda l: l.code == reminder_mollie_method_payment_code)

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
                            'ref': self.reference,
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

    def _create_mollie_order_or_payment(self):
        """ In order to capture payment from mollie we need to create a record on mollie.

        Mollie have 2 type of api to create payment record,
         * order api (used for sales orders)
         * payment api (used for invoices and other payments)

        Different methods suppports diffrent api we choose the api based on that. Also
        we have used payment api as fallback api if order api fails.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        method_record = self.provider_id.mollie_methods_ids.filtered(lambda m: m.method_code == self.mollie_payment_method)

        result = None

        # Order API (use if sale orders are present). Also qr code is only supported by Payment API
        if (not method_record.enable_qr_payment) and 'sale_order_ids' in self._fields and self.sale_order_ids and method_record.supports_order_api:
            # Order API
            result = self._mollie_create_payment_record('order', silent_errors=True)

        # Payment API
        if (result is None or result.get('status') == 422) and method_record.supports_payment_api:  # Here 422 status used for fallback Read more at https://docs.mollie.com/overview/handling-errors
            if result:
                _logger.warning(f"Can not use order api due to 'Error[422]: {result.get('title')} - {result.get('detail')}' \n- Fallback on Mollie payment API ")
            result = self._mollie_create_payment_record('payment')
        return result

    def _mollie_create_payment_record(self, api_type, silent_errors=False):
        """ This method payment/order record in mollie based on api type.

        :param str api_type: api is selected based on this parameter
        :return: data of created record received from mollie api
        :rtype: dict
        """
        payment_data, params = self._mollie_prepare_payment_payload(api_type)
        result = self.provider_id._api_mollie_create_payment_record(api_type, payment_data, params=params, silent_errors=silent_errors)

        # We are setting provider reference as we are receiving it before 3DS payment
        # So we can verify the validity of the transecion
        if result and result.get('id'):
            self.provider_reference = result.get('id')
        return result

    def _mollie_prepare_payment_payload(self, api_type):
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
            'method': self.mollie_payment_method,
            'amount': {
                'currency': self.currency_id.name,
                'value': "%.2f" % (self.amount + self.fees)
            },
            'metadata': {
                'transaction_id': self.id,
                'reference': self.reference,
            },
            'locale': self.provider_id._mollie_user_locale(),
            'redirectUrl': f'{redirect_url}?ref={self.reference}'
        }

        if api_type == 'order':
            # Order api parameters
            order = self.sale_order_ids[0]
            payment_data.update({
                'billingAddress': self._prepare_mollie_address(),
                'orderNumber': f'{_("Sale Order")} ({self.reference})',
                'lines': self._mollie_get_order_lines(order),
            })
        else:
            # Payment api parameters
            payment_data['description'] = self.reference

        # Mollie rejects some local ips/URLs
        # https://help.mollie.com/hc/en-us/articles/213470409
        webhook_url = urls.url_join(base_url, MollieController._webhook_url)
        if "://localhost" not in webhook_url and "://192.168." not in webhook_url and "://127." not in webhook_url:
            payment_data['webhookUrl'] = f'{webhook_url}?ref={self.reference}'

        method_specific_parameters = {}
        # Add if transaction has cardToken
        if self.mollie_card_token:
            method_specific_parameters['cardToken'] = self.mollie_card_token

        # Add if transaction has save card option
        if self.mollie_save_card and not self.env.user.has_group('base.group_public'):  # for security
            user_sudo = self.env.user.sudo()
            mollie_customer_id = user_sudo.mollie_customer_id
            if not mollie_customer_id:
                customer_id_data = self.provider_id._api_mollie_create_customer_id()
                if customer_id_data and customer_id_data.get('id'):
                    user_sudo.mollie_customer_id = customer_id_data.get('id')
                    mollie_customer_id = user_sudo.mollie_customer_id
            if mollie_customer_id:
                method_specific_parameters['customerId'] = mollie_customer_id

        # Add if transaction has issuer
        if self.mollie_payment_issuer:
            method_specific_parameters['issuer'] = self.mollie_payment_issuer

        # Based on api_type pass the method_specific_parameters
        if api_type == 'order':
            payment_data['payment'] = method_specific_parameters
            if payment_data.get('webhookUrl'):
                payment_data['payment']['webhookUrl'] = payment_data['webhookUrl']    # To get refund webhook
        else:
            payment_data.update(method_specific_parameters)
            method_record = self.provider_id.mollie_methods_ids.filtered(lambda m: m.method_code == self.mollie_payment_method)
            if method_record.enable_qr_payment:
                params['include'] = 'details.qrCode'

        return payment_data, params

    def _mollie_get_order_lines(self, order):
        """ This method prepares order line data for order api

        :param order: sale.order record based on this payload will be genrated
        :return: order line data for order api
        :rtype: dict
        """
        lines = []
        for line in order.order_line.filtered(lambda l: not l.display_type):  # ignore notes and section lines
            line_data = {
                'name': line.name,
                'type': 'physical',
                'quantity': int(line.product_uom_qty),    # Mollie does not support float.
                'unitPrice': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_reduce_taxinc
                },
                'totalAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_total,
                },
                'vatRate': "%.2f" % sum(line.tax_id.mapped('amount')),
                'vatAmount': {
                    'currency': line.currency_id.name,
                    'value': "%.2f" % line.price_tax,
                }
            }
            if line.product_id.type == 'service':
                line_data['type'] = 'digital'  # We are considering service product as digital as we don't do shipping for it.

            if 'is_delivery' in line._fields and line.is_delivery:
                line_data['type'] = 'shipping_fee'

            if line.product_id and 'website_url' in line.product_id._fields:
                base_url = self.get_base_url()
                line_data['productUrl'] = urls.url_join(base_url, line.product_id.website_url)

            line_data['metadata'] = {
                'line_id': line.id,
                'product_id': line.product_id.id
            }
            if self.mollie_payment_method == 'voucher':
                category = line.product_id.product_tmpl_id._get_mollie_voucher_category()
                if category:
                    line_data.update({
                        'category': category
                    })
            lines.append(line_data)
        if self.fees:
            lines.append(self._mollie_prepare_fees_line())

        return lines

    def _mollie_prepare_fees_line(self):
        return {
            'name': _('Provider Fees'),
            'type': 'surcharge',
            'metadata': {
                "type": 'surcharge'
            },
            'quantity': 1,
            'unitPrice': {
                'currency': self.currency_id.name,
                'value': "%.2f" % self.fees
            },
            'totalAmount': {
                'currency': self.currency_id.name,
                'value': "%.2f" % self.fees
            },
            'vatRate': "%.2f" % 0.0,
            'vatAmount': {
                'currency': self.currency_id.name,
                'value': "%.2f" % 0.0,
            }
        }

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
        if self.mollie_payment_method == 'billie':
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
        result["country"] = self.partner_country_id and self.partner_country_id.code
        return result

    @api.model
    def _mollie_phone_format(self, phone):
        """ Mollie only allows E164 phone numbers so this method checks whether its validity."""
        phone = False
        if phone:
            try:
                parse_phone = phonenumbers.parse(self.phone, None)
                if parse_phone:
                    phone = phonenumbers.format_number(
                        parse_phone, phonenumbers.PhoneNumberFormat.E164
                    )
            except Exception:
                _logger.warning("Can not format customer phone number for mollie")
        return phone

    def process_refund_transactions_status(self):
        self._process_refund_transactions_status()

    def _process_refund_transactions_status(self):
        self.ensure_one()
        refund_transactions = self.env['payment.transaction'].sudo().search([('source_transaction_id', 'in', self.ids), ('operation', '=', 'refund'), ('state', 'in', ['pending', 'draft'])])
        for transection in refund_transactions:
            if transection.provider_reference:
                source_reference = transection.source_transaction_id.provider_reference
                if source_reference.startswith('ord_'):
                    payment_data = self.provider_id._api_mollie_get_payment_data(source_reference, force_payment=True)
                    source_reference = payment_data.get('id')
                refund_data = transection.provider_id._api_mollie_refund_data(source_reference, transection.provider_reference)
                if refund_data and refund_data.get('id'):
                    if refund_data.get('status') == 'refunded':
                        transection._set_done()
                    elif refund_data.get('status') == 'failed':
                        self._set_canceled("Mollie: " + _("Mollie: failed due to status: %s", refund_data.get('status')))
