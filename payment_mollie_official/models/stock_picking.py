# -*- coding: utf-8 -*-
from mollie.api.client import Client

from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

def get_mollie_provider_key(env):
    provider = self.env['payment.acquirer'].sudo()._get_main_mollie_provider()
    key = provider._get_mollie_api_keys(provider.state)['mollie_api_key']
    return key


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    _mollie_client = Client()

    # Override from the original Odoo function. See
    # https://github.com/odoo/odoo/blob/5c1c092265bfa43167fc2e571642e105be48a060/addons/stock/models/stock_picking.py#L399
    @api.depends('move_type', 'move_lines.state', 'move_lines.picking_id')
    def _compute_state(self):
        ''' State of a picking depends on the state of its related stock.move
        - Draft: only used for "planned pickings"
        - Waiting: if the picking is not ready to be sent so if
          - (a) no quantity could be reserved at all or if
          - (b) some quantities could be reserved and the shipping policy is "deliver all at once"
        - Waiting another move: if the picking is waiting for another move
        - Ready: if the picking is ready to be sent so if:
          - (a) all quantities are reserved or if
          - (b) some quantities could be reserved and the shipping policy is "as soon as possible"
        - Done: if the picking is done.
        - Cancelled: if the picking is cancelled
        '''
        for picking in self:
            if not picking.move_lines:
                picking.state = 'draft'
            elif any(move.state == 'draft' for move in picking.move_lines):
                picking.state = 'draft'
            elif all(move.state == 'cancel' for move in picking.move_lines):
                picking.state = 'cancel'
            elif all(move.state in ['cancel', 'done'] for move in picking.move_lines):
                picking.state = 'done'
                if picking.sale_id.acquirer_method.provider == 'mollie':
                    # We now have to check if the option 'create_shipment_notification is set.
                    provider = self.env['payment.acquirer'].sudo()._get_main_mollie_provider()
                    if provider.create_shipment_notification:
                        key = provider._get_mollie_api_keys(provider.state)['mollie_api_key']
                        self._mollie_client.set_api_key(key)
                        order = self._mollie_client.orders.get(picking.sale_id.acquirer_reference)
                        """
                         See https://docs.mollie.com/reference/v2/shipments-api/create-shipment#example
                         If a picking is set to done in Odoo it means all lines have been delivered.
                         Mollie allows us to pass an empty list [], which will be considered as all products on the
                         current order are delivered to the customer.
                        """
                        shipment = order.create_shipment({
                            'lines': []
                        })
            else:
                relevant_move_state = picking.move_lines._get_relevant_state_among_moves()
                if relevant_move_state == 'partially_available':
                    picking.state = 'assigned'
                else:
                    picking.state = relevant_move_state