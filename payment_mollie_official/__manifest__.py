# -*- coding: utf-8 -*-
# #############################################################################
#
#    Copyright Mollie (C) 2019
#    Contributor: Eezee-It <info@eezee-it.com>
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
{
    'name': 'Mollie Payments',
    'version': '12.0.1',
    'author': 'Mollie & BeOpen',
    'website': 'http://www.mollie.com',
    'category': 'eCommerce',
    'description': """
        Mollie helps businesses of all sizes to sell and build
         more efficiently with a solid but easy-to-use payment solution.
         Start growing your business today with effortless payments.
    """,
    'depends': ["sale", "base", "payment", "website_sale", "website", "web",
                "sale_stock"],
    'data': [
        'data/payment_acquirer_data.xml',
        'data/ir_cron.xml',
        'data/method_data.xml',
        'security/ir.model.access.csv',
        'wizard/force_updates.xml',
        'wizard/config_mollie_view.xml',
        'views/provider_log.xml',
        'views/payment_views.xml',
        'views/sale_order.xml',
        'views/payment_templates.xml',
    ],
    'images': ['static/images/main_screenshot.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
