# -*- coding: utf-8 -*-

{
    'name': 'Mollie Shipment Sync',
    'version': '13.0.0.0',
    'description': '',
    'summary': 'Sync shipment details to mollie payments',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'license': 'LGPL-3',
    'category': '',
    'depends': [
        'sale_management',
        'payment_mollie_official'
    ],
    'data': [
        'views/sale_order.xml',
        'views/payment_acquirer.xml',
        'data/cron.xml'
    ],

    'images': [
        'static/description/cover.png',
    ],
}
