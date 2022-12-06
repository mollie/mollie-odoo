# -*- coding: utf-8 -*-
import logging

from datetime import timedelta, date, datetime
from dateutil.relativedelta import relativedelta
from werkzeug import urls

from odoo import fields, models, api
from odoo.addons.payment_mollie.controllers.main import MollieController

_logger = logging.getLogger(__name__)


class MollieSubscription(models.Model):
    _name = 'mollie.subscription'
    _description = 'Mollie Subscription'
    _inherit = ['mail.thread']

    name = fields.Char(string="Subscription", readonly=True, required=True, copy=False, default='New',
                       tracking=1)
    subscriptions_id = fields.Char('Subscription ID', help="Mollie Subscription ID")
    customerId = fields.Char('Customer ID', help="Customer ID")
    partner_id = fields.Many2one('res.partner', 'Partner')
    status = fields.Char('Status', tracking=1)
    amount = fields.Float('Amount')
    times = fields.Integer('Rebilling Cycle', help="Total number of charges for the subscription to complete")
    timesRemaining = fields.Integer('Remaining Rebilling Cycle',
                                    help="Remaining number of charges for the subscription to complete",
                                    tracking=1)
    interval = fields.Char('Interval', help="A time between charges")
    description = fields.Text('Description')
    startDate = fields.Date('Start Date', tracking=1)
    nextPaymentDate = fields.Date('Next Payment Date', tracking=1)
    product_id = fields.Many2one('product.product', 'Product')
    webhookUrl = fields.Text('webhookUrl')
    mollie_payment_ids = fields.One2many('mollie.payment', 'mollie_subscription_id', string="Payments")
    canceled_date = fields.Datetime('Cancelled Date', tracking=1)
    mandateId = fields.Char('Mandate ID')
    sale_order_id = fields.Many2one('sale.order', 'Sale Order')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('subscriptions.number') or 'New'
        result = super(MollieSubscription, self).create(vals)
        return result

    def _get_start_date(self, product):
        start_date = date.today()
        sub_inter = product and product.subscription_interval
        if product.subscription_interval_type == 'days':
            start_date = date.today() + timedelta(days=int(sub_inter))
        elif product.subscription_interval_type == 'months':
            start_date = date.today() + relativedelta(months=int(sub_inter))
        elif product.subscription_interval_type == 'weeks':
            start_date = date.today() + relativedelta(weeks=int(sub_inter))
        return start_date.strftime("%Y-%m-%d")

    def _mollie_create_subscription(self, transaction_obj):
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        mollie_client = mollie._api_mollie_get_client()
        sale_order_obj = transaction_obj.sale_order_ids
        for product in sale_order_obj.order_line.product_id:
            if product.is_mollie_subscription:
                amount = {'currency': transaction_obj.currency_id.name,
                          'value': "%.2f" % (transaction_obj.amount + transaction_obj.fees)}
                interval = '{} {}'.format(product.subscription_interval, product.subscription_interval_type)
                description = '{} / {}'.format(sale_order_obj.name, product.name)
                webhook_url = ''
                webhookUrl = urls.url_join(mollie.get_base_url(), MollieController._notify_url)
                if "://localhost" not in webhookUrl and "://192.168." not in webhookUrl:
                    webhook_url = webhookUrl
                mollie_customer_id = transaction_obj._get_transaction_customer_id()
                subscription_obj = mollie_client.customer_subscriptions.with_parent_id(mollie_customer_id)
                subscription = subscription_obj.create(data={'amount': amount or '',
                                                             'interval': interval or '',
                                                             'description': description or '',
                                                             'webhookUrl': webhook_url,
                                                             'times': product.interval_time or 1,
                                                             'startDate': self._get_start_date(product)})
                if subscription and subscription['resource'] == 'subscription':
                    vals = {'subscriptions_id': subscription['id'] or False,
                            'customerId': subscription['customerId'] or False,
                            'partner_id': sale_order_obj[0].partner_id.id,
                            'status': subscription['status'] or False,
                            'amount': subscription['amount'] and subscription['amount']['value'] or False,
                            'interval': subscription['interval'] or False,
                            'description': subscription['description'] or False,
                            'startDate': subscription['startDate'] or False,
                            'times': product.interval_time or 1,
                            'nextPaymentDate': subscription['nextPaymentDate'] or False,
                            'product_id': product.id or False,
                            'webhookUrl': subscription['webhookUrl'] or False,
                            'sale_order_id': sale_order_obj.id}
                    subs_obj = self.sudo().create(vals)
                    # sale_order_obj.mollie_subscription_id = subs_obj.id
                    mollie_payment = self.env['mollie.payment'].sudo().search([
                        ('payment_id', '=', transaction_obj.acquirer_reference)])
                    if mollie_payment:
                        mollie_payment.subscription_id = subscription['id']
                        mollie_payment.mollie_subscription_id = subs_obj.id
                        if not mollie_payment.invoice_id:
                            mollie_payment.create_mollie_invoice()

    def refresh_subscription(self):
        self._update_subscriptions_data()
        self._update_payments_data()

    def _update_subscriptions_data(self):
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        mollie_client = mollie._api_mollie_get_client()
        subscription = mollie_client.customer_subscriptions.with_parent_id(self.customerId).get(self.subscriptions_id)
        if subscription:
            self.sudo().write({'status': subscription.get('status', False),
                               'times': subscription.get('times', False),
                               'timesRemaining': subscription.get('timesRemaining', False),
                               'nextPaymentDate': subscription.get('nextPaymentDate', False)})
            msg = f"<b>This subscription has been updated by {self.env.user.name} on " \
                  f"{datetime.today().strftime('%Y-%m-%d %H:%M')}"
            for obj in self:
                obj.sudo().message_post(body=msg)

    def _update_payments_data(self):
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        mollie_client = mollie._api_mollie_get_client()
        payments = mollie_client.customer_payments.with_parent_id(self.customerId).list()
        if payments and payments.get('_embedded'):
            payment_list = payments['_embedded'].get('payments', [])
            mollie_payment_obj = self.env['mollie.payment']
            for payment in payment_list:
                is_exist = mollie_payment_obj.sudo()._get_payment_obj(payment['id'])
                if is_exist:
                    is_exist = is_exist.filtered(lambda l: l.status == 'open')
                    if is_exist.status != payment['status']:
                        is_exist.sudo()._update_payment(payment, self.env.user.name)
                else:
                    mollie_payment_obj.sudo()._create_payment(payment)

    def cancel_subscription(self, **kwargs):
        subscription_id = kwargs.get('sub_id', False)
        if subscription_id:
            subscription_obj = self.sudo().search([('subscriptions_id', '=', subscription_id)])
        else:
            subscription_obj = self

        if subscription_obj:
            subscription_id = subscription_obj.subscriptions_id
            customer_id = subscription_obj.customerId
            mollie = self.env.ref("payment.payment_acquirer_mollie")
            mollie_client = mollie._api_mollie_get_client()
            subscription = mollie_client.customer_subscriptions.with_parent_id(customer_id).delete(subscription_id)
            if subscription:
                canceled_date = False
                if 'canceledAt' in subscription.keys():
                    canceled_date = datetime.strptime(subscription.get('canceledAt')[0:19], "%Y-%m-%dT%H:%M:%S")
                subscription_obj.sudo().write({'status': subscription.get('status', False),
                                               'canceled_date': canceled_date,
                                               'nextPaymentDate': False})
                msg = f"<b>This subscription has been cancelled by {self.env.user.name} on " \
                      f"{datetime.today().strftime('%Y-%m-%d %H:%M')}"
                subscription_obj.sudo().message_post(body=msg)

    def auto_update_subscription(self):
        mollie = self.env.ref("payment.payment_acquirer_mollie")
        mollie_client = mollie._api_mollie_get_client()
        subscriptions = self.sudo().search([('status', '=', 'active')])
        for subs_obj in subscriptions:
            subscription = mollie_client.customer_subscriptions.with_parent_id(subs_obj.customerId).get(
                subs_obj.subscriptions_id)
            if subscription:
                subs_obj.sudo().write({'status': subscription.get('status', False),
                                       'times': subscription.get('times', False),
                                       'timesRemaining': subscription.get('timesRemaining', False),
                                       'nextPaymentDate': subscription.get('nextPaymentDate', False)})
                msg = f"<b>This subscription has been updated by {self.env.user.name} on " \
                      f"{datetime.today().strftime('%Y-%m-%d %H:%M')}"
                subs_obj.sudo().message_post(body=msg)
