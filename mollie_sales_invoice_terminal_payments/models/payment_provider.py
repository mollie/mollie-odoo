# -*- coding: utf-8 -*-

import base64
from odoo import models, fields, _
from odoo.modules.module import get_module_resource


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    mollie_sale_order_terminal_payment_enabled = fields.Boolean(string='Terminal Payment From Sales')
    mollie_account_move_terminal_payment_enabled = fields.Boolean(string='Terminal Payment From Invoice')

    def _get_terminal_api_key(self):
        """
        Retrieve the appropriate Mollie API key based on the current state.

        This method ensures that the correct API key is returned depending on whether
        the instance is in 'test' or 'production' mode.

        If payment_mollie_official is installed then the instance has a 'mollie_api_key_test'
        field returned in test mode.

        Returns:
            str or bool: The appropriate Mollie API key if available, otherwise False.
        """
        self.ensure_one()
        mollie_api_key = self.mollie_api_key_test if self.state == 'test' else self.mollie_api_key
        return mollie_api_key or False

    def action_open_terminal_list(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Mollie Terminals'),
            'res_model': 'mollie.payments.terminal',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_mollie_provider_id': self.id}
        }

    def action_mollie_sync_methods(self):
        super().action_mollie_sync_methods()
        pos_method = self.with_context(active_test=False).mollie_methods_ids.filtered(lambda method: method.method_code == 'pointofsale')
        if pos_method and not pos_method.active:
            pos_method.active = True
        if not pos_method:
            icon = self.env['payment.icon'].search([('name', '=', 'Mollie terminal')], limit=1)
            if not icon:
                image_path = get_module_resource('mollie_sales_invoice_terminal_payments', 'static/img', 'method-icon.png')
                icon = self.env['payment.icon'].create({
                    'name': 'Mollie terminal',
                    'image': base64.b64encode(open(image_path, 'rb').read())
                })
            self.env['mollie.payment.method'].create({
                'name': 'Mollie terminal',
                'method_code': 'pointofsale',
                'supports_payment_api': True,
                'provider_id': self.id,
                'active_on_shop': False,
                'payment_icon_ids': [(6, 0, [icon.id])],
                'country_ids': [(
                    6, 0, (
                        self.env.ref('base.be') +
                        self.env.ref('base.nl') +
                        self.env.ref('base.de') +
                        self.env.ref('base.at') +
                        self.env.ref('base.ch') +
                        self.env.ref('base.fr') +
                        self.env.ref('base.uk') +
                        self.env.ref('base.it') +
                        self.env.ref('base.es') +
                        self.env.ref('base.pt') +
                        self.env.ref('base.se') +
                        self.env.ref('base.dk') +
                        self.env.ref('base.fi') +
                        self.env.ref('base.pl') +
                        self.env.ref('base.bg') +
                        self.env.ref('base.hr') +
                        self.env.ref('base.cy') +
                        self.env.ref('base.cz') +
                        self.env.ref('base.ee') +
                        self.env.ref('base.gr') +
                        self.env.ref('base.hu') +
                        self.env.ref('base.is') +
                        self.env.ref('base.ie') +
                        self.env.ref('base.lv') +
                        self.env.ref('base.lt') +
                        self.env.ref('base.li') +
                        self.env.ref('base.lu') +
                        self.env.ref('base.mt') +
                        self.env.ref('base.ro') +
                        self.env.ref('base.sk') +
                        self.env.ref('base.si')
                    ).ids
                )]
            })
