# -*- coding: utf-8 -*-
import json
from odoo import http, tools
from odoo.http import request


class MollieData(http.Controller):

    @http.route('/get_mollie_order_info', type='json', auth='user')
    def get_order_info(self, order_id, journal_id):
        AccountJournal = request.env["account.journal"]
        return AccountJournal.browse(journal_id)._api_call_get_order_meta(order_id)