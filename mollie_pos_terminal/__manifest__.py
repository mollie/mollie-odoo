{
    'name': 'Mollie POS Terminal',
    'version': '20.0.1.0.0',
    'summary': 'Connect your POS with Mollie terminals',
    'author': 'Mollie',
    'maintainer': 'Droggol Infotech Private Limited',
    'license': 'LGPL-3',
    'category': 'Point of Sale',
    'depends': [
        'point_of_sale', 'pos_mollie'
    ],
    'data': [
        'security/ir.access.csv',
        'views/mollie_pos_terminal_payments_views.xml',
        'views/mollie_pos_terminal_views.xml',
        'views/pos_mollie_voucher_views.xml',
        'views/pos_payment_method_views.xml',
        'wizard/pos_payment_views.xml',
        'views/payment_provider_views.xml',
        'wizard/mollie_sync_terminal.xml',
    ],
    'assets': {
        'point_of_sale.payment_terminals': [
            'mollie_pos_terminal/static/src/app/utils/payment/payment_mollie.js'
        ],
        'point_of_sale._assets_pos': [
            'mollie_pos_terminal/static/**/*'
        ],
    },
    'installable': True,
    'images': [
        'static/description/cover.png',
    ],
}
