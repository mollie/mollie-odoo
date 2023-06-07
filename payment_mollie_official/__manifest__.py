# -*- coding: utf-8 -*-

{
    'name': 'Mollie Payments Extended',
    'version': '16.0.0.1',
    'category': 'eCommerce',
    'license': 'LGPL-3',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'website': 'https://www.mollie.com/',

    'summary': 'Add extra features in mollie payment',
    'description': """
        Add extra features in mollie payment
    """,

    'depends': [
        'payment_mollie', 'product', 'account'
    ],
    'external_dependencies': {},
    'data': [
        'security/ir.model.access.csv',
        'views/payment_views.xml',
        'views/payment_transaction.xml',
        'views/payment_mollie_templates.xml',
        'views/account_move_view.xml',
        'views/account_payment_register.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'payment_mollie_official/static/src/js/payment_form.js',
            'payment_mollie_official/static/src/js/qr_dialog.js',
            'payment_mollie_official/static/src/scss/payment_form.scss',
        ]
    },

    'images': [
        'static/description/cover.png',
    ],
}
