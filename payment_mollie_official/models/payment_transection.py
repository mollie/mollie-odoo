# -*- coding: utf-8 -*-

import logging
import pytz
import dateutil.parser

from odoo import http, tools
from odoo.http import request
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mollie_payment_token = fields.Char()
    mollie_payment_method = fields.Char()
    mollie_payment_issuer = fields.Char()
    mollie_reminder_payment_id = fields.Many2one('account.payment', string='Reminder Payment', readonly=True)

    def mollie_create(self, vals):
        create_vals = {}

        if request and request.params.get('mollie_payment_token'):
            create_vals['mollie_payment_token'] = request.params.get('mollie_payment_token')

        if request and request.params.get('paymentmethod'):
            create_vals['mollie_payment_method'] = request.params.get('paymentmethod')

        if request and request.params.get('mollie_issuer'):
            create_vals['mollie_payment_issuer'] = request.params.get('mollie_issuer')

        return create_vals

    def _mollie_form_get_tx_from_data(self, data):
        acquirer_reference = data.get("id")
        transaction = self.search([("acquirer_reference", "=", acquirer_reference)])
        if len(transaction) != 1:
            error_msg = _("Mollie:received response for reference %s") % (transaction.reference)
            if not transaction:
                error_msg += _(": no order found")
            else:
                error_msg += _(": multiple order found")
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return transaction

    def _mollie_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        if self.acquirer_reference and data.get('id') != self.acquirer_reference:
            invalid_parameters.append(('Transaction Id', data.get('id'), self.acquirer_reference))

        # TODO: Not that important but check orders or invoices if possible

        # Check what transection is with same amount
        amount = data.get('amount')
        if amount and float_compare(float(amount.get('value', '0.0')), self.amount, 2) != 0:
            invalid_parameters.append(('Amount', amount.get('value'), '%.2f' % self.amount))
        if amount.get('currency') != self.currency_id.name:
            invalid_parameters.append(('Currency', data.get('currency'), self.currency_id.name))

        return invalid_parameters

    def _mollie_form_validate(self, data):
        acquirer_reference = data.get("id")

        if self.state == "done":
            _logger.info("Mollie: already validated transection (ref %s)", self.reference)
            return True

        # TODO: [PGA] check this is need or not
        mollie_payment = self.acquirer_id._mollie_get_payment_data(acquirer_reference)

        # Validate through order via its sub payment object as it has valid error messages
        # and state We are assuming it will have only one payment as we are createing new order
        # for every order
        if mollie_payment.get('resource') == 'order' and mollie_payment.get('_embedded'):
            payment_list = mollie_payment['_embedded'].get('payments', [])
            if len(payment_list):
                mollie_payment = payment_list[0]

        try:
            # dateutil and pytz don't recognize abbreviations PDT/PST
            tzinfos = {"PST": -8 * 3600, "PDT": -7 * 3600}
            validation_date = dateutil.parser.parse(data.get('createdAt'), tzinfos=tzinfos).astimezone(pytz.utc).replace(tzinfo=None)

        except Exception:
            validation_date = fields.Datetime.now()

        state = mollie_payment.get('status')
        if state in ['authorized', 'paid']:
            self._set_transaction_done()
            self.write({'date': validation_date})
        elif state in ["canceled", "expired", "failed"]:
            self._set_transaction_cancel()
        elif state in ["open", "pending"]:
            self._set_transaction_pending()
        else:
            msg = "Error %s %s" % (acquirer_reference, self.reference)
            self._set_transaction_error(msg)

        return True

    def _create_payment(self, add_payment_vals={}):
        """ Set diffrent journal based on payment method"""
        add_payment_vals = add_payment_vals or {}
        if self.acquirer_id.provider == 'mollie':
            method = self.acquirer_id.mollie_methods_ids.filtered(lambda m: m.method_id_code == self.mollie_payment_method)
            if method and method.journal_id:
                add_payment_vals['journal_id'] = method.journal_id.id

            # handle special cases for vouchers
            if method.method_id_code == 'voucher':

                # We need to get payment information because transection with "voucher" method
                # might paid with multiple payment method. So we need to payment data to check
                # how payment is done.
                mollie_payment = self.acquirer_id._mollie_get_payment_data(self.acquirer_reference)

                # When payment is done via order API
                if mollie_payment.get('resource') == 'order' and mollie_payment.get('_embedded'):
                    payment_list = mollie_payment['_embedded'].get('payments', [])
                    if len(payment_list):
                        mollie_payment = payment_list[0]

                remainder_method_code = mollie_payment['details'].get('remainderMethod')
                if remainder_method_code:  # if there is remainder amount
                    primary_journal = method.journal_id or self.acquirer_id.journal_id
                    remainder_method = self.acquirer_id.mollie_methods_ids.filtered(lambda m: m.method_id_code == remainder_method_code)
                    remainder_journal = remainder_method.journal_id or self.acquirer_id.journal_id

                    # if both journals are diffrent then we need to split the payment
                    if primary_journal != remainder_journal:
                        voucher_amount = sum([float(voucher['amount']['value']) for voucher in mollie_payment['details']['vouchers']])
                        voucher_amount = tools.float_round(voucher_amount, precision_digits=2)

                        add_payment_vals['amount'] = voucher_amount
                        voucher_payment = super()._create_payment(add_payment_vals=add_payment_vals)

                        add_payment_vals['amount'] = float(mollie_payment['details']['remainderAmount']['value'])
                        add_payment_vals['journal_id'] = remainder_journal.id
                        remainder_payment = super()._create_payment(add_payment_vals=add_payment_vals)

                        self.payment_id = voucher_payment
                        self.mollie_reminder_payment_id = remainder_payment

                        return voucher_payment

        return super()._create_payment(add_payment_vals=add_payment_vals)

    def mollie_manual_payment_validation(self):
        """ This method helps when you want to process
            delayed transections manually. This method
            will be called from transection form view.
        """
        self.ensure_one()
        if self.state not in ['done', 'cancel']:
            data = self.acquirer_id._mollie_get_payment_data(self.acquirer_reference)
            self.form_feedback(data, "mollie")
        if self.state == 'done' and not self.is_processed:
            self._post_process_after_done()
