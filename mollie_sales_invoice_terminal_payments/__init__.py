# -*- coding: utf-8 -*-

from . import models
from . import wizard


def post_init_hook(env):
    """ Create `payment.method` records for the installed payment providers. """
    existing_method = env['payment.method'].with_context(active_test=False).search([('code', '=', 'pointofsale')], limit=1)
    mollie_providers = env['payment.provider'].with_context(active_test=False).search([('code', '=', 'mollie')])
    if existing_method and mollie_providers:
        existing_method.write({
            'provider_ids': [(6, 0, mollie_providers.ids)],
        })
