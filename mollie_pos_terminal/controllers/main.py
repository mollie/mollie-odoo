# coding: utf-8
import logging
import json
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosMollieController(http.Controller):

    @http.route('/pos_mollie/webhook', type='http', methods=['POST'], auth='public', csrf=False)
    def webhook(self, **post):
        if not post.get('id'):
            return
        request.env['mollie.pos.terminal.payments']._mollie_process_webhook(post)
        return ""
