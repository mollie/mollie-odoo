# -*- coding: utf-8 -*-
# #############################################################################
#
#    Copyright Eezee-It (C) 2018
#    Author: Eezee-It <info@eezee-it.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import fields, models, api, _
from odoo.exceptions import UserError

ACQUIRER_MODELS = ["sale.order", "payment.transaction"]


class force_update_data(models.TransientModel):
    _name = "force.update.data"
    _description = "Force Update Data"

    acquirer_reference = fields.Char(string=u"Acquirer Reference Id")

    @api.multi
    def force_update(self):
        self.ensure_one()
        context = dict(self._context or {})
        active_id = context.get("active_id", False)
        active_model = context.get("active_model", False)
        if active_id and active_model:
            record = self.env[active_model].browse(active_id)
            if active_model in ACQUIRER_MODELS:
                record.acquirer_reference = self.acquirer_reference
            else:
                raise UserError(
                    _(
                        "This template does not belong to authorized Models"
                        " for changing the 'acquirer_reference' field, please"
                        " contact your administrator!"
                    )
                )
        return True
