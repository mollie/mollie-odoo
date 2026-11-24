# -*- coding: utf-8 -*-

from odoo import fields, models, api, _, Command
from odoo.exceptions import ValidationError


class MolliePaymentsTerminalWizard(models.TransientModel):
    _name = 'mollie.payments.terminal.wizard'
    _description = 'Mollie Payments Terminal Wizard'

    move_id = fields.Many2one('account.move', string='Invoice')
    amount_residual = fields.Monetary(string='Amount (Residual)', currency_field='currency_id', related='move_id.amount_residual',
                                      readonly=False, store=True)
    order_id = fields.Many2one('sale.order', string='Sale Order')
    amount_total = fields.Monetary(string='Amount (Total)', currency_field='currency_id', related='order_id.amount_total',
                                   readonly=False, store=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency', readonly=True)
    terminal_id = fields.Many2one('mollie.payments.terminal', string='Mollie Terminal', required=True, domain="[('company_id', '=', company_id), ('status', '=', 'active')]")

    def terminal_confirm(self):
        eur = self.env.ref('base.EUR')
        if not eur.active:
            raise ValidationError(_('Please make sure that Euro(€) Currency is activated.'))

        custom_create_values = {}

        if self.move_id:
            custom_create_values.update({'invoice_ids': [Command.set([self.move_id.id])]})

        if self.order_id:
            custom_create_values.update({'sale_order_ids': [Command.set([self.order_id.id])]})

        provider = self.terminal_id.sudo().provider_id
        payment_method = provider.with_context(active_test=False).payment_method_ids.filtered(lambda pm: pm.code == 'pointofsale')

        if not provider:
            raise ValidationError(_('Payment provider "Mollie" not found.'))
        if not payment_method:
            raise ValidationError(_('Payment method "Mollie POS" not found.'))

        PaymentTransaction = self.env['payment.transaction'].sudo()
        prefix = self.order_id.name if self.order_id else self.move_id.name
        reference = PaymentTransaction._compute_reference(provider.code, prefix)

        transaction = PaymentTransaction.create({
            'provider_id': provider.id,
            'payment_method_id': payment_method.id,
            'reference': reference,
            'amount': self.amount_total if self.order_id else self.amount_residual,
            'currency_id': self.currency_id.id,
            'partner_id': self.order_id.partner_id.id if self.order_id else self.move_id.partner_id.id,
            'terminal_id': self.terminal_id.id,
            'operation': 'online_redirect',
            **(custom_create_values or {}),
        })

        if self.order_id:
            if self.amount_total > self.order_id.amount_total or self.amount_total <= 0:
                raise ValidationError(_('Please make sure that Amount is less than sale order Amount Due and greater than 0.'))
        if self.move_id:
            if self.amount_residual > self.move_id.amount_residual or self.amount_residual <= 0:
                raise ValidationError(_('Please make sure that Amount is less than invoice Amount Due and greater than 0.'))

        transaction._mollie_terminal_api_make_payment_request()
