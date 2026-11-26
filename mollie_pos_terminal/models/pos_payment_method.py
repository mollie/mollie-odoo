from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    mollie_pos_terminal_id = fields.Many2one(
        'mollie.pos.terminal',
        string='Mollie Pos Terminal',
        help="Terminals are synced from Point of Sale > Configuration > Mollie Pos Terminal.",
        domain="[('status', '=', 'active'), ('provider_id', '=', mollie_payment_provider_id)]",
        compute='_compute_mollie_pos_terminal_id',
        inverse='_inverse_mollie_pos_terminal_id',
    )
    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('sport_culture', 'Sports & Culture'),
    ], string='Voucher Category', copy=False)

    @api.depends('mollie_payment_provider_id', 'mollie_terminal_id')
    def _compute_mollie_pos_terminal_id(self):
        Terminal = self.env['mollie.pos.terminal']
        for rec in self:
            terminal = False
            if rec.mollie_payment_provider_id and rec.mollie_terminal_id:
                terminal = Terminal.search([
                    ('provider_id', '=', rec.mollie_payment_provider_id.id),
                    ('terminal_id', '=', rec.mollie_terminal_id),
                    ('status', '=', 'active'),
                ], limit=1)
            rec.mollie_pos_terminal_id = terminal

    def _inverse_mollie_pos_terminal_id(self):
        for rec in self:
            rec.mollie_terminal_id = rec.mollie_pos_terminal_id.terminal_id or False

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result += ['mollie_voucher_category']
        return result

    @api.model
    def _load_pos_self_data_domain_and_relations(self, data):
        # The kiosk can't limit a voucher to the order's eligible products: keep voucher methods off it.
        # Not in `_load_pos_self_data_domain`: pos_self_order overrides that one without calling super.
        result = super()._load_pos_self_data_domain_and_relations(data)
        result['domain'] = result['domain'] + [
            '|', ('payment_provider', '!=', 'mollie'), ('mollie_voucher_category', '=', False),
        ]
        return result

    def _allowed_actions_in_self_order(self):
        # The kiosk only creates and polls payments: it never refunds or cancels.
        return [
            action for action in super()._allowed_actions_in_self_order()
            if action not in ('mollie_create_refund', 'mollie_cancel_payment')
        ]

    def mollie_create_payment(self, amount: float, payment_uuid: str, pos_session_id: int, order_uuid: str | None = None):
        """Override of `pos_mollie` to add the voucher lines (see payment.provider._send_api_request)
        and log the payment with its order (see `mollie_get_order_payments`)."""
        # mollie_pos: identify the call as this module's (see payment.provider._build_request_headers).
        payment = super(PosPaymentMethod, self.with_context(
            mollie_pos=True,
            mollie_voucher_category=self.mollie_voucher_category,
        )).mollie_create_payment(amount, payment_uuid, pos_session_id)
        self.env['mollie.pos.terminal.payments'].sudo()._mollie_log(
            payment, self, payment_uuid, pos_session_id, order_uuid=order_uuid)
        return payment

    def mollie_create_refund(self, original_payment_id: str, amount: float, payment_uuid: str, pos_session_id: int):
        """Override of `pos_mollie` to log the refund."""
        # mollie_pos: identify the call as this module's (see payment.provider._build_request_headers).
        refund = super(PosPaymentMethod, self.with_context(mollie_pos=True)).mollie_create_refund(
            original_payment_id, amount, payment_uuid, pos_session_id)
        Log = self.env['mollie.pos.terminal.payments'].sudo()
        original = Log.search([('name', '=', original_payment_id)], limit=1)
        Log._mollie_log(refund, self, payment_uuid, pos_session_id, original)
        return refund

    def mollie_get_payment(self, payment_id: str):
        """Override of `pos_mollie` to include the refunds and keep the payment log current.
        Called by the POS while it waits, and by `pos_mollie`'s webhook."""
        self.ensure_one()
        self._check_mollie_access_right()
        # sudo: the API key is restricted to base.group_system.
        payment = self.sudo().mollie_payment_provider_id.with_context(mollie_pos=True)._send_api_request(
            "GET", f"/payments/{payment_id}", params={"embed": "refunds"})
        self.env['mollie.pos.terminal.payments'].sudo()._mollie_update(payment)
        return payment

    def mollie_get_order_payments(self, order_uuid: str):
        """The Mollie payments made for a POS order, oldest first, as Mollie last returned them,
        with the uuid of the line that made each and its payment method. The POS makes the order's
        lines match them (see syncMollieOrder). Payments still in progress are asked again first:
        a missed webhook leaves their stored status behind."""
        self._check_mollie_access_right()
        if not order_uuid:
            return []
        logged_payments = self.env['mollie.pos.terminal.payments'].sudo().search([
            ('order_uuid', '=', order_uuid), ('parent_payment_id', '=', False),
        ])
        for logged_payment in logged_payments.filtered(lambda p: p.status in ('open', 'pending')):
            logged_payment.payment_method_id.mollie_get_payment(logged_payment.name)
        return [{
            **logged_payment.mollie_latest_response,
            'payment_uuid': logged_payment.mollie_uid,
            'payment_method_id': logged_payment.payment_method_id.id,
        } for logged_payment in logged_payments]
