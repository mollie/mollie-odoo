from odoo import models, fields
from datetime import datetime


class MollieLog(models.Model):
    _name = 'mollie.log'
    _rec_name = "log_name"
    _description = "Mollie Subscription Logging"

    log_name = fields.Char("Name")
    log_description = fields.Text("Description")
    processed_date = fields.Datetime("Date", copy=False, help="Date when log created.")
    user = fields.Char("User")

    def add_log(self,name, description):
        if name and description:
            self.sudo().create({'log_name': name,
                                'log_description': description,
                                'processed_date':datetime.today(),
                                'user': self.env.user.name or 'System'})
            print('Log added for : {}'.format(name))
