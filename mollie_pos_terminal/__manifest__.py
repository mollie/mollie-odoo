{
    'name': 'Mollie Pos Terminal',
    'version': '14.0.0.1',
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
        'views/assets.xml',
        'views/mollie_pos_terminal_views.xml',
        'views/mollie_pos_terminal_payments_views.xml',
        'views/res_config_settings_views.xml',
        'views/pos_payment_method_views.xml',
        'wizard/mollie_sync_terminal.xml',
    ],
    'qweb': [
        'static/src/views/*.xml',
    ],
    'images': [
        'static/description/cover.png',
    ],
}
