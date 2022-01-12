# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mollie_payment = fields.Boolean(compute='_compute_mollie_payment')
    mollie_need_shipment_sync = fields.Boolean(compute='_compute_mollie_need_shipment_sync', store=True, default=False)

    def mollie_sync_shipment_data(self):
        transaction = self._mollie_get_valid_transaction()
        if transaction:
            data = transaction.acquirer_id._api_mollie_get_payment_data(transaction.acquirer_reference)
            shipment_lines = []
            if data and data.get('lines'):
                for mollie_line in data.get('lines'):
                    mollie_line_metadata = mollie_line.get('metadata')
                    if mollie_line_metadata:
                        order_line = self.order_line.filtered(lambda l: l.id == mollie_line_metadata.get('line_id'))
                        if order_line and order_line.qty_delivered > mollie_line['quantityShipped']:
                            qty_to_ship = order_line.qty_delivered - mollie_line['quantityShipped']
                            if qty_to_ship and mollie_line.get('shippableQuantity') >= qty_to_ship:
                                shipment_lines.append({
                                    'id': mollie_line['id'],
                                    'quantity': int(qty_to_ship)    # mollie does not support float values
                                })
                if shipment_lines:
                    transaction.acquirer_id._api_mollie_sync_shipment(transaction.acquirer_reference, {'lines': shipment_lines})

        # For all the cases we will un-mark the sales orders
        self.mollie_need_shipment_sync = False

    def _compute_mollie_payment(self):
        for order in self:
            valid_transaction = order._mollie_get_valid_transaction()
            order.mollie_payment = len(valid_transaction) >= 1

    @api.depends('order_line.qty_delivered')
    def _compute_mollie_need_shipment_sync(self):
        for order in self:
            if order.mollie_payment:
                order.mollie_need_shipment_sync = True
            else:
                order.mollie_need_shipment_sync = False

    def _mollie_get_valid_transaction(self):
        self.ensure_one()
        return self.transaction_ids.filtered(lambda t: t.acquirer_id.provider == 'mollie' and t.state in ['authorized', 'done'] and t.acquirer_reference.startswith("ord_"))

    def _cron_mollie_sync_shipment(self):
        mollie_acquirer = self.env.ref('payment.payment_acquirer_mollie')
        if mollie_acquirer.mollie_auto_sync_shipment:
            orders = self.search([('mollie_need_shipment_sync', '=', True)])
            for order in orders:
                order.mollie_sync_shipment_data()
                self.env.cr.commit()
        return True
