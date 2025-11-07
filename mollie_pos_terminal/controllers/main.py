# coding: utf-8

from odoo import http
from odoo.http import request


class PosMollieController(http.Controller):

    @http.route([
        '/pos_mollie/webhook/<string:order_type>',
    ], type='http', methods=['POST'], auth='public', csrf=False)
    def webhook(self, order_type='pos', **post):
        if not post.get('id'):
            return
        request.env['mollie.pos.terminal.payments']._mollie_process_webhook(post, order_type)
        return ""
