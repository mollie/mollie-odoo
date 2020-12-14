# -*- coding: utf-8 -*-

{
    'name': 'Mollie Settlement Sync',
    'version': '14.0.1.1',
    'description': '',
    'summary': 'This module sync settlements from mollie',
    'author': 'Mollie',
    'maintainer': 'Applix',
    'license': 'LGPL-3',
    'category': '',
    'depends': [
        'account_accountant'
    ],
    'data': [
        'views/account_journal.xml',
        'views/bank_statement.xml',
        'views/templates.xml',
        'wizard/mollie_init_views.xml',
        'security/ir.model.access.csv'
    ],
    "qweb": ['static/src/xml/*.xml'],

    'images': [
        'static/description/cover.png',
    ],
}
