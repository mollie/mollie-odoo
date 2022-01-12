# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from mollie.api.error import UnprocessableEntityError


class PaymentAcquirerMollie(models.Model):
    _inherit = 'payment.acquirer'

    mollie_auto_sync_shipment = fields.Boolean()

    # -----------------------------------------------
    # Methods that uses to mollie python lib
    # -----------------------------------------------

    def _api_mollie_sync_shipment(self, order_reference, shipment_data):
        return self._mollie_make_request(f'/orders/{order_reference}/shipments', data=shipment_data, method="POST")
