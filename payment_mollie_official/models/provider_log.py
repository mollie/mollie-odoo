# -*- coding: utf-8 -*-
# #############################################################################
#
#    Copyright Eezee-It (C) 2019
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
import datetime
import logging
from odoo import fields, models, api, _

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
_logger = logging.getLogger(__name__)

EXCEPTION_LOG_TYPE = {
    ('red', _("Danger")),
    ('olive', _("Warning")),
    ('gray', _("Info")),
    ('green', _("Success")),
}


class ProviderLog(models.Model):
    _name = "provider.log"
    _order = "id desc"

    name = fields.Char(string="Description", required=True)
    detail = fields.Html(string="Detail",)
    origin = fields.Char(string="Origin", default='mollie', readonly=True)
    type = fields.Selection(EXCEPTION_LOG_TYPE, string="Type",
                            default='gray', readonly=True, required=True)

    @api.model
    def clean_old_logging(self, days=90):
        """
        Function called by a cron to clean old loggings.
        @return: True
        """
        last_days = datetime.datetime.now() +\
            datetime.timedelta(days=-days)
        domain = [
            ('create_date', '<', last_days.strftime(
                DEFAULT_SERVER_DATETIME_FORMAT))
        ]
        logs = self.search(domain)
        logs.unlink()
        message = " %d logs are deleted" % (len(logs))
        return self._post_log({'name': message})

    @api.model
    def _post_log(self, vals):
        self.create(vals)
        self.env.cr.commit()
