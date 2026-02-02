# -*- coding: utf-8 -*-

from odoo import models, fields, Command, api, _
from odoo.exceptions import ValidationError


class PaymentCaptureWizard(models.TransientModel):
    _inherit = 'payment.capture.wizard'

    mollie_wizard_line_ids = fields.One2many('mollie.payment.capture.wizard.line', 'wizard_id', string='Wizard Line', compute='_compute_mollie_wizard_lines', readonly=False, store=True)
    mollie_amount_to_capture = fields.Monetary(compute='_compute_mollie_amount_to_capture', string='Amount To Capture (Mollie)')

    @api.depends('mollie_wizard_line_ids')
    def _compute_mollie_amount_to_capture(self):
        for wizard in self:
            wizard.mollie_amount_to_capture = sum(wizard.mollie_wizard_line_ids.mapped('capture_amount'))

    @api.depends('available_amount', 'mollie_amount_to_capture')
    def _compute_amount_to_capture(self):
        for wizard in self:
            if wizard.mollie_wizard_line_ids:
                wizard.amount_to_capture = wizard.mollie_amount_to_capture
                wizard._compute_is_amount_to_capture_valid()
            else:
                super(PaymentCaptureWizard, wizard)._compute_amount_to_capture()

    @api.depends('transaction_ids')
    def _compute_mollie_wizard_lines(self):
        for wizard in self:
            mollie_transactions = wizard.transaction_ids._origin.filtered(lambda t: t.provider_id.code == 'mollie' and t.state in ['authorized', 'done'] and t.provider_reference.startswith("ord_"))
            wizard_lines = []
            for transaction in mollie_transactions:
                data = transaction.provider_id._api_mollie_get_payment_data(transaction.provider_reference)
                if data and data.get('lines'):
                    for mollie_line in data.get('lines'):
                        if mollie_line.get('status') == 'canceled':
                            continue
                        mollie_line_metadata = mollie_line.get('metadata')
                        if mollie_line_metadata and 'sale_order_ids' in transaction._fields:
                            order_line = transaction.sale_order_ids.order_line.filtered(lambda line: line.id == mollie_line_metadata.get('line_id'))
                            if order_line:
                                capture_qty = order_line.qty_delivered - mollie_line['quantityShipped']
                                if mollie_line['shippableQuantity'] > 0:
                                    wizard_lines.append(Command.create({
                                        'price_reduce_taxinc': order_line.price_reduce_taxinc,
                                        'product_id': order_line.product_id.id,
                                        'capturable_qty': mollie_line['shippableQuantity'],
                                        'transaction_id': transaction.id,
                                        'mollie_id': mollie_line['id'],
                                        'capture_qty': capture_qty if capture_qty > 0 else 0,
                                    }))
            wizard.mollie_wizard_line_ids = wizard_lines

    def action_mollie_capture(self):
        for wizard in self:
            for transaction in wizard.transaction_ids:
                capturable_lines = wizard.mollie_wizard_line_ids.filtered(lambda line: line.transaction_id == transaction and line.capture_qty > 0)
                capture_lines = [{
                    'id': line.mollie_id,
                    'quantity': int(line.capture_qty)    # mollie does not support float values
                }for line in capturable_lines if line.capture_qty > 0]
                if capture_lines:
                    transaction.provider_id._api_mollie_sync_shipment(transaction.provider_reference, {'lines': capture_lines})
                if wizard.void_remaining_amount and capturable_lines:
                    transaction._send_void_request()


class MolliePaymentCaptureWizardLine(models.TransientModel):
    _name = 'mollie.payment.capture.wizard.line'
    _description = 'Mollie payment capture wizard line'

    capturable_qty = fields.Float('Capturable Qty', readonly=True)
    capture_qty = fields.Float('Capture Qty')
    void_amount = fields.Float(compute='_compute_void_amount', string='Void Amount')
    wizard_id = fields.Many2one('payment.capture.wizard', string='wizard')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    capture_amount = fields.Monetary(compute='_compute_capture_amount', string='Capture Amount')
    transaction_id = fields.Many2one('payment.transaction', string='Transaction')
    mollie_id = fields.Char('Mollie Id')
    product_id = fields.Many2one('product.product', string='Product')
    price_reduce_taxinc = fields.Monetary(string='Unit Price')

    @api.depends('capturable_qty', 'capture_qty', 'price_reduce_taxinc')
    def _compute_void_amount(self):
        for line in self:
            line.void_amount = (line.capturable_qty - line.capture_qty) * line.price_reduce_taxinc

    @api.depends('capture_qty', 'price_reduce_taxinc')
    def _compute_capture_amount(self):
        for line in self:
            line.capture_amount = line.capture_qty * line.price_reduce_taxinc

    @api.constrains('capture_qty', 'capturable_qty')
    def _check_capture_qty(self):
        for line in self:
            if line.capture_qty > line.capturable_qty:
                raise ValidationError(_('The capture qty must be less than or equal to the Deliverable Qty.'))
