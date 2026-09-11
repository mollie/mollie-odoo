# -*- coding: utf-8 -*-

{
    'name': 'Mollie Direct Payments Terminal',
    'version': '18.0.0.5.0',
    'description': '',
    'summary': 'Pay Sales orders & Invoices seamlessly via Mollie Terminal',
    'author': 'Mollie',
    'maintainer': 'Droggol Infotech Private Limited',
    'license': 'OPL-1',
    'depends': [
        'sale_management', 'account', 'payment_mollie'
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'wizard/mollie_sync_payments_terminal.xml',
        'wizard/mollie_payments_terminal_wizard.xml',
        'views/account_move_view.xml',
        'views/sale_order_view.xml',
        'views/mollie_payments_terminal_views.xml',
        'views/payment_provider_views.xml',
        'data/payment_method.xml'
    ],
    'post_init_hook': 'post_init_hook',
    'images': [
        'static/description/cover.png',
    ],
}
