import logging
from datetime import datetime
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MolliePayment(models.Model):
    _name = 'mollie.payment'
    _description = 'Mollie Payment'
    _inherit = ['mail.thread']

    name = fields.Char(string="Payment", readonly=True, required=True, copy=False, default='New')
    payment_id = fields.Char(string='Payment ID', help="Mollie Payment ID")
    createdAt = fields.Datetime(string='Date')
    amount = fields.Float(string='Amount', tracking=1)
    amount_currency = fields.Char(string='Currency')
    description = fields.Text(string='Description')
    method = fields.Char(string='Method')
    metadata = fields.Text(string='Metadata')
    status = fields.Char(string='Status', tracking=1)
    paid_date = fields.Datetime(string='Paid Date', tracking=1)
    profileId = fields.Char(string='Profile ID')
    customerId = fields.Char(string='Customer ID')
    mandateId = fields.Char(string='Mandate ID', tracking=1)
    subscription_id = fields.Char(string='Subscription ID', tracking=1)
    sequence_type = fields.Char(string='Type', tracking=1)
    settlement_amount = fields.Float(string='Settlement Amount', tracking=1)
    settlement_currency = fields.Char(string='Settlement Currency')
    details = fields.Text(string='Details')
    mollie_subscription_id = fields.Many2one("mollie.subscription", string="Subscription", tracking=1)
    checkout_url = fields.Text(string='Checkout URL', tracking=1)
    invoice_id = fields.Many2one("account.move")
    transaction_id = fields.Many2one("payment.transaction")

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('payment.number') or 'New'
        log_sudo = self.env['mollie.log'].sudo()
        log_sudo.add_log("Prepare Payment in Odoo", f"vals : {vals}")
        result = super(MolliePayment, self).create(vals)
        log_sudo.add_log("Created Payment in Odoo", f"Payment Object : {result}")
        return result

    def _create_payment(self, pay_obj):
        """Create payment record in odoo"""
        if pay_obj:
            paid_date = datetime.strptime(pay_obj['createdAt'][0:19], "%Y-%m-%dT%H:%M:%S")
            if pay_obj.get('paidAt', False):
                paid_date = datetime.strptime(pay_obj['paidAt'][0:19], "%Y-%m-%dT%H:%M:%S")
            mollie_subs_id = self.env['mollie.subscription'].search(
                [('subscriptions_id', '=', pay_obj.get('subscriptionId', False))])
            log_sudo = self.env['mollie.log'].sudo()
            checkout_url = False
            if pay_obj.get('status') == 'open':
                checkout_url = pay_obj["_links"]["checkout"]["href"]
            vals = {'payment_id': pay_obj['id'] or False,
                    'createdAt': pay_obj['createdAt'] and datetime.strptime(pay_obj['createdAt'][0:19],
                                                                            "%Y-%m-%dT%H:%M:%S") or False,
                    'amount': pay_obj.get('amount', {}).get("value", ""),
                    'amount_currency': pay_obj.get('amount', {}).get("currency", ""),
                    'description': pay_obj['description'] or False,
                    'method': pay_obj['method'] or False,
                    'metadata': pay_obj['metadata'] or False,
                    'status': pay_obj['status'] or False,
                    'paid_date': paid_date or False,
                    'profileId': pay_obj['profileId'] or False,
                    'customerId': pay_obj['customerId'] or False,
                    'mandateId': pay_obj.get('mandateId', False),
                    'subscription_id': pay_obj.get('subscriptionId', False),
                    'sequence_type': pay_obj['sequenceType'] or False,
                    'settlement_amount': pay_obj.get('settlementAmount', {}).get("value", 0.0),
                    'settlement_currency': pay_obj.get('settlementAmount', {}).get("currency", 0.0),
                    'details': pay_obj.get('details', False),
                    'mollie_subscription_id': mollie_subs_id and mollie_subs_id.id or False,
                    'checkout_url': checkout_url,
                    "transaction_id": pay_obj['metadata'] and pay_obj.get("metadata", {}).get("transaction_id")}
            log_sudo.add_log("Preparing Data for Create Mollie Payment in Odoo", f"vals : {vals}")
            payment = self.sudo().create(vals)
            log_sudo.add_log("Created Mollie Payment in Odoo", f"Created Object : {payment}")
            msg = "<b>This payment has been created by %s on %s" % (self.env.user.name,
                                                                    datetime.today().strftime('%Y-%m-%d %H:%M'))
            for obj in self:
                obj.sudo().message_post(body=msg)
            payment.create_mollie_invoice()

    def _get_payment_obj(self, payment_id):
        """Get payment data from odoo"""
        log_sudo = self.env['mollie.log'].sudo()
        payment_obj = self.sudo().search([('payment_id', '=', payment_id)])
        log_sudo.add_log("Get payment Object", f"Payment Object : {payment_obj}")
        return payment_obj if payment_obj else {}

    def refresh_payment(self):
        """Reload payment data using API"""
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        log_sudo = self.env['mollie.log'].sudo()
        mollie_client = mollie._api_mollie_get_client()
        pay_obj = mollie_client.payments.get(self.payment_id)
        if pay_obj:
            log_sudo.add_log("Refresh Payment | Update Payment", f"Payment Object : {pay_obj}")
            self._update_payment(pay_obj, self.env.user.name)

    def _update_payment(self, pay_obj, method):
        """Update payment record from payment data"""
        if pay_obj:
            paid_date = datetime.strptime(pay_obj['createdAt'][0:19], "%Y-%m-%dT%H:%M:%S")
            if pay_obj.get('paidAt', False):
                paid_date = datetime.strptime(pay_obj['paidAt'][0:19], "%Y-%m-%dT%H:%M:%S")
            vals = {'amount': pay_obj['amount'] and pay_obj['amount']['value'] or False,
                    'amount_currency': pay_obj.get('amount', {}).get("currency", ""),
                    'metadata': pay_obj['metadata'] or False,
                    'status': pay_obj['status'] or False,
                    'paid_date': paid_date or False,
                    'settlement_amount': pay_obj.get('settlementAmount', {}).get("value", 0.0),
                    'settlement_currency': pay_obj.get('settlementAmount', {}).get("currency", 0.0),
                    'details': pay_obj.get('details', False),
                    "transaction_id": pay_obj['metadata'] and pay_obj.get("metadata", {}).get("transaction_id")}
            if pay_obj.get('subscriptionId', False):
                vals.update({'subscription_id': pay_obj.get('subscriptionId')})
            log_sudo = self.env['mollie.log'].sudo()
            log_sudo.add_log("Update Payment", f"Vals : {vals}")
            self.sudo().write(vals)
            msg = f"<b>This payment has been updated by %s on %s" % (method,
                                                                     datetime.today().strftime('%Y-%m-%d %H:%M'))
            for obj in self:
                obj.sudo().message_post(body=msg)

    def auto_update_payments(self):
        """Cron job for update and create a payment records from Mollie API"""
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        log_sudo = self.env['mollie.log'].sudo()
        log_sudo.add_log("Auto Update Payments Called", "Auto Update Payments Called")
        mollie_client = mollie._api_mollie_get_client()
        subscription_objs = self.env['mollie.subscription'].search([('status', '=', 'active')])
        customer_ids = list(set(subscription_objs.mapped('customerId')))
        for customer_id in customer_ids:
            payments = mollie_client.customer_payments.with_parent_id(customer_id).list()
            if payments and payments.get('_embedded'):
                payment_list = payments['_embedded'].get('payments', [])
                for payment in payment_list:
                    payment_objs = self.sudo()._get_payment_obj(payment['id'])
                    if payment_objs:
                        payment_obj = payment_objs.filtered(lambda l: l.status not in ['paid', 'expired',
                                                                                       'canceled', 'failed'])
                        if payment_obj and payment_obj.status != payment['status']:
                            log_sudo.add_log("Auto Update Payments", f"Transaction Object : {payment}")
                            payment_obj.sudo()._update_payment(payment, self.env.user.name)
                    else:
                        self.sudo()._create_payment(payment)

    def create_mollie_invoice(self):
        """
        Creates invoice for each created payment.
        @author: Maulik Barad on Date 01-Dec-2022.
        """
        invoice = False
        subscription = self.mollie_subscription_id
        log_sudo = self.env['mollie.log'].sudo()
        if subscription:
            if self.sequence_type == "first":
                order = subscription.sale_order_id
                if order.state == "draft":
                    order.action_confirm()
                if not order.invoice_ids:
                    invoice = order._create_invoices()
            else:
                invoice_vals = self._prepare_invoice_vals()
                invoice = self.env["account.move"].create(invoice_vals)
            if invoice:
                log_sudo.add_log("Create Mollie Invoice",
                                 f"Invoice Object : {invoice} | Subscription Id : {subscription}")
                invoice.action_post()
                self.invoice_id = invoice

    def pay_mollie_invoice(self):
        """
        Register payment for the related invoice.
        @author: Maulik Barad on Date 01-Dec-2022.
        """
        log_sudo = self.env['mollie.log'].sudo()
        vals = self._prepare_payment_dict(self.invoice_id)
        log_sudo.add_log("Account Payment", f"vals : {vals}")
        payment = self.env["account.payment"].create(vals)
        log_sudo.add_log("Created Account Payment", f"payment object : {payment}")
        payment.action_post()
        self.reconcile_payment_ept(payment, self.invoice_id)
        return True

    def _prepare_payment_dict(self, invoice):
        """
        Prepares payment vals for invoice
        @author: Maulik Barad on Date 01-Dec-2022.
        """
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        payment_method = mollie.mollie_methods_ids.filtered(lambda x: x.method_code == self.method)
        return {
            'journal_id': invoice.journal_id.id,
            'ref': self.payment_id,
            'currency_id': invoice.currency_id.id,
            'payment_type': 'inbound',
            'date': invoice.date,
            'partner_id': invoice.partner_id.id,
            'amount': invoice.amount_residual,
            'payment_method_id': payment_method.id,
            'partner_type': 'customer'
        }

    def _prepare_invoice_vals(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        journal = self.env['account.move'].with_context(default_move_type='out_invoice')._get_default_journal()
        if not journal:
            raise UserError(
                _('Please define an accounting sales journal for the company %s (%s).', self.company_id.name,
                  self.company_id.id))

        currency = self.env["res.currency"].search([("name", "=", self.amount_currency)])

        transaction_id = self.transaction_id
        if not transaction_id:
            transaction_id = self.env["payment.transaction"].search([("acquirer_reference", "=", self.payment_id)])
        invoice_vals = {
            'ref': self.payment_id or '',
            'move_type': 'out_invoice',
            'currency_id': currency.id,
            'partner_id': self.mollie_subscription_id.partner_id.id,
            'journal_id': journal.id,
            'invoice_origin': self.name,
            # 'payment_reference': self.reference,
            'transaction_ids': [(6, 0, transaction_id.ids)],
            'invoice_line_ids': [(0, 0, {
                'product_id': self.mollie_subscription_id.product_id.id,
                'name': self.name,
                'product_uom_id': self.mollie_subscription_id.product_id.uom_id.id,
                'quantity': 1.0,
                'price_unit': self.amount,
            })],
        }
        return invoice_vals
