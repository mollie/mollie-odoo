from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PosMakePayment(models.TransientModel):
    _inherit = 'pos.make.payment'

    payment_provider = fields.Selection(related='payment_method_id.payment_provider')

    # Checkbox for user to opt-in for Mollie refund
    refund_via_mollie = fields.Boolean(
        string='Refund via Mollie',
        default=False,
        help="Check this box to process the refund through Mollie"
    )

    # Transaction ID from original order's Mollie payment
    mollie_transaction_id = fields.Char(
        string='Mollie Transaction ID',
        compute='_compute_mollie_transaction_id',
    )

    # Max refund amount fetched from Mollie (stored, set via onchange)
    mollie_max_refund_amount = fields.Float(
        string='Max Mollie Refund Amount',
    )

    # Error message (stored, set via onchange)
    mollie_refund_error = fields.Char(
        string='Mollie Refund Error',
    )

    @api.depends('payment_method_id')
    def _compute_mollie_transaction_id(self):
        """Get Mollie transaction ID from original order's payment."""
        for wizard in self:
            wizard.mollie_transaction_id = False

            if wizard.payment_method_id.payment_provider != 'mollie':
                continue

            refund_order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
            if not refund_order or not refund_order.refunded_order_id:
                continue

            order = refund_order.refunded_order_id

            # Find Mollie payment matching the selected payment method
            mollie_payment = order.payment_ids.filtered(
                lambda line: line.transaction_id
                and line.payment_method_id.payment_provider == 'mollie'
                and line.payment_method_id == wizard.payment_method_id
            )

            if len(mollie_payment) == 1:
                wizard.mollie_transaction_id = mollie_payment.transaction_id

    @api.onchange('refund_via_mollie', 'payment_method_id')
    def _onchange_refund_via_mollie(self):
        """Fetch max refund amount from Mollie when checkbox is toggled on."""
        if self.payment_provider != 'mollie':
            self.refund_via_mollie = False
        self.mollie_max_refund_amount = 0.0
        self.mollie_refund_error = ''

        if not self.refund_via_mollie:
            return

        if not self.mollie_transaction_id:
            self.mollie_refund_error = _('No or Multiple Mollie transactions found for this payment method.')
            return

        try:
            payment = self.payment_method_id.mollie_get_payment(self.mollie_transaction_id)
        except UserError as e:
            self.mollie_refund_error = _('Failed to fetch Mollie payment status: %s', e)
            return

        remaining_amount = float(payment.get('amountRemaining', {}).get('value', 0))

        if remaining_amount <= 0:
            self.mollie_refund_error = _('No remaining amount to refund from Mollie. Already fully refunded.')
            return

        self.mollie_max_refund_amount = remaining_amount

    @api.onchange('amount', 'refund_via_mollie', 'mollie_max_refund_amount')
    def _onchange_amount_validate_mollie(self):
        """Validate refund amount against max Mollie refund when checkbox is on."""
        if not self.refund_via_mollie or not self.mollie_max_refund_amount:
            return

        if abs(self.amount) > self.mollie_max_refund_amount:
            self.mollie_refund_error = _(
                'Refund amount (%(amount).2f) exceeds maximum refundable (%(max_amount).2f)',
                amount=abs(self.amount),
                max_amount=self.mollie_max_refund_amount
            )
        else:
            self.mollie_refund_error = ''

    def check(self):
        """Process the refund, optionally via Mollie."""
        self.ensure_one()

        # If not refunding via Mollie, use standard flow
        if not self.refund_via_mollie:
            return super().check()

        # Validate Mollie refund conditions
        if self.mollie_refund_error:
            raise UserError(self.mollie_refund_error)

        if not self.mollie_transaction_id:
            raise UserError(_('No Mollie transaction ID found.'))

        if self.mollie_max_refund_amount <= 0:
            raise UserError(_('No refundable amount available from Mollie.'))

        if abs(self.amount) > self.mollie_max_refund_amount:
            raise UserError(_(
                'Refund amount (%(amount)s) exceeds maximum refundable amount from Mollie (%(max_amount)s)',
                amount=abs(self.amount),
                max_amount=self.mollie_max_refund_amount
            ))

        if self.amount > 0:
            raise UserError(_(
                'Refund amount must be negative when refunding via Mollie.'
            ))

        refund_order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
        payments_before = refund_order.payment_ids

        # Validate and record the payment in Odoo first, call Mollie last: if the
        # refund fails it raises and everything rolls back, and if Odoo fails no
        # money has left yet.
        res = super().check()

        refund_payment = refund_order.payment_ids - payments_before
        refund = self.payment_method_id.mollie_create_refund(
            self.mollie_transaction_id, abs(refund_payment.amount), refund_payment.uuid, refund_order.session_id.id)
        refund_payment.transaction_id = refund['id']
        return res
