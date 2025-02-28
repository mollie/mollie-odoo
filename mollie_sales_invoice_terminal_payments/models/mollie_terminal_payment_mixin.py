# -*- coding: utf-8 -*-

from odoo import fields, models


class MollieTerminalPaymentMixin(models.AbstractModel):
    _name = 'mollie.terminal.payment.mixin'

    mollie_terminal_payment_enabled = fields.Boolean(string='Mollie Sale', compute='_compute_mollie_terminal_details')
    mollie_terminal_active_transaction = fields.Boolean(string='Mollie Open Payment', compute='_compute_mollie_terminal_details')

    def _compute_mollie_terminal_details(self):
        for record in self:
            record.mollie_terminal_payment_enabled = False
            record.mollie_terminal_active_transaction = False
            mollie_provider = self.env['payment.provider'].sudo().search([('code', '=', 'mollie'), ('state', '!=', 'disabled')])
            field_name = f"mollie_{self._name.replace('.', '_')}_terminal_payment_enabled"
            if field_name not in mollie_provider._fields:
                continue

            if record_transactions := record.transaction_ids:
                record.mollie_terminal_active_transaction = record_transactions.filtered(lambda t: t.provider_code == 'mollie' and t.state in ['draft', 'pending']) or False

                # TODO: In sales you can only do payment once. Implement this in the future to handle multiple transections too. Invoice have amount_residual but sale have nothing like that.
                if record._name == 'sale.order':
                    if record_transactions.filtered(lambda t: t.state == 'done'):
                        continue

            if mollie_provider and mollie_provider.filtered(lambda provider: provider[field_name]):
                record.mollie_terminal_payment_enabled = True

    def action_mollie_terminal_payment(self):
        view = self.env.ref('mollie_sales_invoice_terminal_payments.mollie_payments_terminal_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mollie.payments.terminal.wizard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': self._get_mollie_terminal_payment_context()
        }

    def action_mollie_terminal_payment_status(self):
        # webhook will call from Mollie So this button just use to refresh the page
        return True

    def _get_mollie_terminal_payment_context(self):
        return {
            **self._context
        }
