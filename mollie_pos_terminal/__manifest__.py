{
    'name': 'Mollie Pos Terminal',
    'version': '16.0.0.2',
    'description': '',
    'summary': 'Connect your pos with mollie terminal',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'license': 'LGPL-3',
    'category': '',
    'depends': [
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mollie_pos_terminal_views.xml',
        'views/mollie_pos_terminal_payments_views.xml',
        'views/res_config_settings_views.xml',
        'views/pos_payment_method_views.xml',
        'wizard/mollie_sync_terminal.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mollie_pos_terminal/static/src/views/*.js',
            'mollie_pos_terminal/static/src/views/*.xml',
        ],
        'point_of_sale.assets': [
            'mollie_pos_terminal/static/src/js/*'
        ],
    },
    'images': [
        'static/description/cover.png',
    ],
}
