# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


# -----------------------------------------------
# Clean old view if user came from old version
# -----------------------------------------------

def migrate(cr, version):
    """ This will delete old views """
    env = api.Environment(cr, SUPERUSER_ID, {})

    old_views_refs = ['payment_mollie_official.acquirer_form_mollie']
    for view_id in old_views_refs:
        old_view = env.ref(view_id, raise_if_not_found=False)
        if old_view:
            old_view.unlink()
            _logger.info("Mollie: deleted view from older version view_id '%s' " % view_id)
