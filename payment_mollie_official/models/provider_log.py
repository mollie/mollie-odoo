# -*- coding: utf-8 -*-
import datetime
import logging
from odoo import fields, models, api

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

_logger = logging.getLogger(__name__)


class ProviderLog(models.Model):
    _name = "provider.log"
    _description = "Mollie provider log details"
    _order = "id desc"

    name = fields.Char(string="Description", required=True)
    detail = fields.Html(string="Detail")
    origin = fields.Char(string="Origin", default="mollie", readonly=True)
    """
        In case you wonder why the keys for this selection are so odd..
        This was initially created by another developer in V10/V11/V12.
        For backwards compatibility and easier migration I've kept the keys
        identical. Otherwise users who upgrade would need data migration too.
    """
    type = fields.Selection(
        [
            ("red", "Error"),
            ("olive", "Warning"),
            ("gray", "Info"),
            ("green", "Succes"),
        ],
        string="Type",
        default="gray",
        readonly=True,
        required=True,
    )

    @api.model
    def clean_old_logging(self, days=90):
        """
        Function called by a cron to clean old loggings.
        @return: True
        """
        last_days = datetime.datetime.now() + datetime.timedelta(days=-days)
        domain = [
            (
                "create_date",
                "<",
                last_days.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
            )
        ]
        logs = self.search(domain)
        logs.unlink()
        message = " %d logs are deleted" % (len(logs))
        return self._post_log({"name": message})

    @api.model
    def _post_log(self, vals):
        self.create(vals)
        self.env.cr.commit()
