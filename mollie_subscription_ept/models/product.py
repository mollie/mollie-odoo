import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_mollie_subscription = fields.Boolean('Is Subscription Product')
    subscription_interval = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6'),
                                              ('7', '7'), ('8', '8'), ('9', '9'), ('10', '10'), ('11', '11'), ('12', '12')])
    subscription_interval_type = fields.Selection([('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months')])
    interval_time = fields.Integer('Times')
