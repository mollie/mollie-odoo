# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MolliePaymentMethod(models.Model):
    _inherit = 'mollie.payment.method'

    def _mollie_show_creditcard_option(self):
        """
        override the existing method of the mollie official payment gateway module
        """
        if self.method_code != 'creditcard':
            return False
        acquirer = self.sudo().acquirer_id
        if acquirer.mollie_profile_id and acquirer.sudo().mollie_use_components:
            return True
        return False
