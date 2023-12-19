# -*- coding: utf-8 -*-

{
    'name': 'Mollie Balance Sync',
    'version': '17.0.0.0',
    'description': '',
    'summary': 'This module sync balances from mollie',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'license': 'LGPL-3',
    'category': '',
    'depends': [
        'account_accountant'
    ],
    'data': [
        'data/cron.xml',
        'security/ir.model.access.csv',
        'views/mollie_transaction_queue_views.xml',
        'views/account_journal.xml',
        'views/bank_statement.xml',
        'wizard/sync_mollie_statement_line_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mollie_balance_sync/static/src/xml/*.xml',
            'mollie_balance_sync/static/src/js/info_widget.js',
        ]
    },
}
