# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api


logger = logging.getLogger(__name__)


class ConfigMollie(models.TransientModel):
    _name = "config.mollie"
    _description = "Set up config mollie"

    def _get_default_acquirer_id(self):
        return self.env['payment.acquirer']._get_main_mollie_provider()

    acquirer_id = fields.Many2one('payment.acquirer', 'Acquirer',
                                  default=_get_default_acquirer_id,
                                  required=True)
    mollie_api_key_test = fields.Char(
        'Mollie Test API key', size=40, required_if_provider='mollie')
    mollie_api_key_prod = fields.Char('Mollie Live API key', size=40,
                                      default="Mollie Live API key",
                                      required_if_provider='mollie')
    message = fields.Text('Message')

    def have_mollie_account(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window'].for_xml_id(
            'payment_mollie_official', 'mollie_install_config_set_keys_action')
        action['res_id'] = self.id
        return action

    def no_mollie_account(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_url',
            'url': 'https://www.mollie.com/dashboard/signup',
            'target': 'new',
        }
        return action

    def apply_config_mollie_account(self):
        self.ensure_one()
        self.acquirer_id.write({
            'mollie_api_key_test': self.mollie_api_key_test,
            'mollie_api_key_prod': self.mollie_api_key_prod,
            'website_published': True})
        self.acquirer_id.update_available_mollie_methods()
        return {
            'name': 'Mollie',
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': self.acquirer_id.id,
            'res_model': 'payment.acquirer',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'context': {
                'form_view_ref':
                    'payment.acquirer_form'
            }
        }
