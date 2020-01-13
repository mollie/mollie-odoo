# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError

ACQUIRER_MODELS = ["sale.order", "payment.transaction"]


class ForceUpdateData(models.TransientModel):
    _name = "force.update.data"
    _description = "Force Update Data"

    acquirer_reference = fields.Char(string="Acquirer Reference Id")

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
