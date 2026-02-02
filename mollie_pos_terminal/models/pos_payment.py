from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class PosPayment(models.Model):
    _inherit = "pos.payment"

    mollie_uid = fields.Char(string='Mollie UID', copy=False)

class DrPosMakePayment(models.TransientModel):
    _inherit = 'pos.make.payment'

    use_payment_terminal = fields.Selection(related='payment_method_id.use_payment_terminal')
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

            if wizard.payment_method_id.use_payment_terminal != 'mollie':
                continue

            refund_order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
            if not refund_order or not refund_order.refunded_order_id:
                continue

            order = refund_order.refunded_order_id

            # Find Mollie payment matching the selected payment method
            mollie_payment = order.payment_ids.filtered(
                lambda line: line.transaction_id
                and line.payment_method_id.use_payment_terminal == 'mollie'
                and line.payment_method_id == wizard.payment_method_id
            )

            if len(mollie_payment) == 1:
                wizard.mollie_transaction_id = mollie_payment.transaction_id

    @api.onchange('refund_via_mollie', 'payment_method_id')
    def _onchange_refund_via_mollie(self):
        """Fetch max refund amount from Mollie when checkbox is toggled on."""
        self.mollie_max_refund_amount = 0.0
        self.mollie_refund_error = ''

        if not self.refund_via_mollie:
            return

        if not self.mollie_transaction_id:
            self.mollie_refund_error = _('No Mollie transaction found for this payment method.')
            return

        # Call Mollie API to get payment status
        try:
            payment_status = self.payment_method_id.mollie_pos_terminal_id._api_get_mollie_payment_status(
                self.mollie_transaction_id
            )
        except Exception as e:
            self.mollie_refund_error = _('Failed to fetch Mollie payment status: %s') % str(e)
            return

        if not payment_status or payment_status.get('error'):
            self.mollie_refund_error = payment_status.get('detail', _('Failed to fetch Mollie payment status'))
            return

        remaining_amount =  float(payment_status.get('amountRemaining', {}).get('value', 0))

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
                'Refund amount (%(amount)s) exceeds maximum refundable (%(max_amount)s)',
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
                'Refund amount must be nagative when refunding via Mollie.'
            ))

        # Get refund order and original order
        refund_order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
        order = refund_order.refunded_order_id

        if self.payment_method_id.split_transactions and not refund_order.partner_id:
            raise UserError(_(
                "Customer is required for %s payment method.",
                self.payment_method_id.name
            ))

        # Prepare refund request data
        refund_data = {
            'mollie_origin_transaction_id': self.mollie_transaction_id,
            'curruncy': order.currency_id.name,
            'amount': self.amount,
            'payment_method_id': self.payment_method_id.id,
            'order_type': 'pos',
            'mollie_uid': False,
            'order_id': order.uuid,
            'session_id': order.session_id.id,
            'description': order.name,
        }

        # Send refund request to Mollie
        result = self.payment_method_id.mollie_pos_terminal_id._api_make_refund_request(
            refund_data
        )
        if result.get('resource') != 'refund':
            raise ValidationError(_("Mollie refund failed: %s") % result.get('detail', _('Unknown error')))

        transaction_id = result.get('id')
        self = self.with_context(mollie_refund_transaction_id=transaction_id)
        return super(DrPosMakePayment, self).check()