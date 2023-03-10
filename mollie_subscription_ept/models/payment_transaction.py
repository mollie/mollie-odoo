import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_transaction_customer_id(self):
        mollie_customer_id = False
        partner_obj = False
        if self.sale_order_ids and self.sale_order_ids[0]:
            order_source = self.sale_order_ids[0]
            partner_obj = order_source.partner_id
        if partner_obj and partner_obj.mollie_customer_id:
            mollie_customer_id = partner_obj.mollie_customer_id
        elif partner_obj:
            customer_id_data = self.acquirer_id._api_mollie_create_customer_id(partner_obj)
            if customer_id_data and customer_id_data.get('id'):
                mollie_customer_id = customer_id_data.get('id')
                partner_obj.write({'mollie_customer_id': mollie_customer_id})
        return mollie_customer_id

    def _process_feedback_data(self, data):
        """
        Overriden method for
        @author: Maulik Barad on Date 25-Nov-2022.
        """
        if self.provider != 'mollie':
            return super()._process_feedback_data(data)

        mollie_payment_obj = self.env['mollie.payment']
        log_sudo = self.env['mollie.log'].sudo()

        self._process_refund_transactions_status()

        # if self.state == 'done':
        #     return

        acquirer_reference = self.acquirer_reference
        mollie_payment = self.acquirer_id._api_mollie_get_payment_data(acquirer_reference)
        payment_status = mollie_payment.get('status')
        log_sudo.add_log("Mollie Payment", f"Mollie Payment Object : {mollie_payment}")
        if payment_status == 'paid' or payment_status == 'pending' or payment_status == 'authorized':
            log_sudo.add_log("Start Creating Subscription", "Start Creating Subscription")
            self.env['mollie.subscription']._mollie_create_subscription(self)
            log_sudo.add_log("Created Subscription", "Created Subscription")
        if payment_status == 'paid':
            self._set_done()
        elif payment_status == 'pending':
            self._set_pending()
        elif payment_status == 'authorized':
            self._set_authorized()
        elif payment_status in ['expired', 'canceled', 'failed']:
            existing_payment = mollie_payment_obj._get_payment_obj(mollie_payment['id'])
            if existing_payment:
                existing_payment = existing_payment.filtered(lambda l: l.status == 'open')
                if existing_payment.status != mollie_payment['status']:
                    existing_payment._update_payment(mollie_payment, 'Webhook')
            else:
                log_sudo.add_log("Start Creating Payment", f"Payment Data : {mollie_payment}")
                mollie_payment_obj._create_payment(mollie_payment)
            self._set_canceled("Mollie: " + _("Mollie: canceled due to status: %s", payment_status))
        else:
            _logger.info("Received data with invalid payment status: %s", payment_status)
            self._set_error("Mollie: " + _("Received data with invalid payment status: %s", payment_status))

    def _create_mollie_order_or_payment(self):
        """
        Overriden this method for handing the subscription type order. Also creating the custom mollie payment record.
        @author: Maulik Barad on Date 25-Nov-2022.
        """
        self.ensure_one()
        method_record = self.acquirer_id.mollie_methods_ids.filtered(lambda m: m.method_code == self.mollie_payment_method)

        result = None
        log_sudo = self.env['mollie.log'].sudo()

        subscription_product = self.sale_order_ids.order_line.product_id.filtered(lambda prd: prd.is_mollie_subscription)
        if subscription_product and method_record.supports_payment_api and method_record.supports_order_api:
            result = self.with_context(first_mollie_payment=True)._mollie_create_payment_record('payment')
            if result:
                log_sudo.add_log("Start Creating Payment", f"Payment Data : {result}")
                self.env['mollie.payment'].sudo()._create_payment(result)
        else:
            # Order API (use if sale orders are present). Also qr code is only supported by Payment API
            if (not method_record.enable_qr_payment) and 'sale_order_ids' in self._fields and self.sale_order_ids and method_record.supports_order_api:
                # Order API
                log_sudo.add_log("Start Creating Payment", "Start Creating Payment")
                result = self._mollie_create_payment_record('order', silent_errors=True)
                log_sudo.add_log("Created Payment Object", f"Payment Object : {result}")

            # Payment API
            if (result is None or result.get('status') == 422) and method_record.supports_payment_api:  # Here 422 status used for fallback Read more at https://docs.mollie.com/overview/handling-errors
                if result:
                    _logger.warning("Can not use order api due to 'Error[422]: %s - %s' "
                                    "\n- Fallback on Mollie payment API " % (result.get('title'),
                                                                             result.get('detail')))
                log_sudo.add_log("Start Creating Payment", "Start Creating Payment")
                result = self._mollie_create_payment_record('payment')
                log_sudo.add_log("Created Payment Object", f"Payment Object : {result}")
        return result

    def _mollie_prepare_payment_payload(self, api_type):
        """
        Inherited method for updating the customer of payment data.
        @author: Maulik Barad on Date 25-Nov-2022.
        """
        payment_data, params = super(PaymentTransaction, self)._mollie_prepare_payment_payload(api_type)

        if self._context.get("first_mollie_payment"):
            payment_data.update({'description': f'First payment for {self.sale_order_ids.name}', 'sequenceType': 'first'})

        mollie_customer_id = self._get_transaction_customer_id()
        if api_type == 'order':
            payment_data['payment']["customerId"] = mollie_customer_id
        else:
            payment_data["customerId"] = mollie_customer_id

        return payment_data, params
