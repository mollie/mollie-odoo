from odoo import _, fields, models
from odoo.exceptions import ValidationError

LIST_TERMINAL_PAGER_LIMIT = 250


class MolliePosTerminal(models.Model):
    _name = 'mollie.pos.terminal'
    _description = 'Mollie Pos Terminal'

    name = fields.Char()
    terminal_id = fields.Char('Terminal ID')
    provider_id = fields.Many2one('payment.provider', required=True)
    profile_id = fields.Char('Profile ID')
    serial_number = fields.Char('Serial Number')
    status = fields.Selection([
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive')
    ])
    currency_id = fields.Many2one('res.currency', string='Currency')
    company_id = fields.Many2one(related='provider_id.company_id', store=True)

    # ==============
    # ACTION METHODS
    # ==============

    def action_sync_terminals(self):
        # `default_provider_id` is set when the list is opened from a Mollie provider.
        provider_id = self.env.context.get('default_provider_id')
        return {
            "name": _("Sync Terminal"),
            "type": "ir.actions.act_window",
            "res_model": "sync.mollie.terminal",
            "target": "new",
            "views": [[False, "form"]],
            "context": {"default_provider_id": provider_id} if provider_id else {},
        }

    def _sync_mollie_terminals(self, provider_id):
        existing_terminals = self.search([('provider_id', '=', provider_id.id)])
        synced_terminals = self.browse()

        for terminal in self._api_get_terminals(provider_id):
            terminal_found = existing_terminals.filtered(lambda x: x.terminal_id == terminal['id'])
            currency = self.env['res.currency'].search([('name', '=', terminal['currency'])])

            if not currency:
                raise ValidationError(_('Currency %s is not active. Please activate it first.', terminal['currency']))

            terminal_data = {
                'name': terminal['description'],
                'terminal_id': terminal['id'],
                'profile_id': terminal['profileId'],
                'provider_id': provider_id.id,
                'serial_number': terminal['serialNumber'],
                'status': terminal['status'],
                'currency_id': currency.id
            }
            if terminal_found:
                terminal_found.write(terminal_data)
                synced_terminals |= terminal_found
            else:
                synced_terminals |= self.create(terminal_data)
        # Mollie no longer lists these for this key (key moved to another profile/account, test<->live switch).
        (existing_terminals - synced_terminals).status = 'inactive'
        return synced_terminals

    # =================
    # API CALLS METHODS
    # =================

    def _api_get_terminals(self, provider):
        """ Fetch all terminals from the Mollie API, following its pagination links. """
        terminals_data = []
        endpoint, params = '/terminals', {'limit': LIST_TERMINAL_PAGER_LIMIT}
        while endpoint:
            # sudo: the API key is restricted to base.group_system.
            result = provider.sudo().with_context(mollie_pos=True)._send_api_request('GET', endpoint, params=params)
            terminals_data += result.get('_embedded', {}).get('terminals', [])
            next_link = (result.get('_links') or {}).get('next')
            # The next link is a full URL that already carries `from` and `limit`.
            endpoint, params = next_link and next_link['href'], None
        return terminals_data
