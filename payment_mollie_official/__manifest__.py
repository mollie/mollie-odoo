# -*- coding: utf-8 -*-

{
    'name': 'Mollie Payments',
    'version': '12.0.1.1',
    'category': 'eCommerce',
    'license': 'LGPL-3',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'website': 'https://www.mollie.com/',

    'summary': 'Accept online payments with mollie. Start growing your business with effortless payments.',
    'description': """
        Accept online payments with mollie. Start growing your business with effortless payments.',
    """,

    'depends': [
        'payment'
    ],
    'external_dependencies': {
        'python': ['mollie']
    },
    'data': [
        'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/payment_mollie_templates.xml',
        'data/payment_acquirer_data.xml',
    ],

    'images': [
        'static/description/cover.png',
    ],
}
