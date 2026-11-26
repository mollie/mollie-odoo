from odoo import fields, models, release


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    mollie_terminal_count = fields.Integer(compute='_compute_mollie_terminal_count')

    def _compute_mollie_terminal_count(self):
        counts = dict(self.env['mollie.pos.terminal']._read_group(
            [('provider_id', 'in', self.ids)], ['provider_id'], ['__count']))
        for provider in self:
            provider.mollie_terminal_count = counts.get(provider, 0)

    def action_view_mollie_terminals(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('mollie_pos_terminal.mollie_pos_terminal_action')
        action.update({
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        })
        return action

    def _has_mollie_api_key(self):
        """Whether this provider has an API key. Safe for any user: only a boolean leaves it."""
        provider_sudo = self.sudo()
        if not provider_sudo:
            return False
        # Our payment_mollie_official adds a separate test key, used while the provider isn't live.
        if provider_sudo._fields.get('mollie_api_key_test') and not provider_sudo.is_live:
            return bool(provider_sudo.mollie_api_key_test)
        return bool(provider_sudo.mollie_api_key)

    def _build_request_headers(self, *args, **kwargs):
        """Override of `payment_mollie` to identify this module's calls (flagged with the
        `mollie_pos` context key) to Mollie: https://docs.mollie.com/integration-partners/user-agent-strings"""
        headers = super()._build_request_headers(*args, **kwargs)
        if self.code == 'mollie' and self.env.context.get('mollie_pos'):
            module_version = self.env.ref('base.module_mollie_pos_terminal').installed_version
            headers['User-Agent'] = f"Odoo/{release.version} MolliePOSOdoo/{module_version}"
        return headers

    def _send_api_request(self, method, endpoint, *, json=None, **kwargs):
        """Override of `payment` to add the lines Mollie needs for a voucher payment, as
        `pos_mollie` builds and sends the POS payment request in one method."""
        if category := self.env.context.get('mollie_voucher_category'):
            if method == 'POST' and endpoint == '/payments':
                json = {**json, 'lines': [{
                    'description': 'Voucher payment',
                    'quantity': 1,
                    'unitPrice': json['amount'],
                    'totalAmount': json['amount'],
                    'categories': [category],
                }]}
        return super()._send_api_request(method, endpoint, json=json, **kwargs)
