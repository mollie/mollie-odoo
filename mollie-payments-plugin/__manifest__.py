# -*- encoding: utf-8 -*-
{
    'name': 'Mollie Odoo plugin',
    'version': '1.0',
    'author': 'Mollie & BeOpen',
    'website': 'http://www.mollie.com',
    'category': 'eCommerce',
    'description': "",
    'depends': ['payment','website_sale'],
    'data': [
        'views/mollie.xml',
        'views/payment_acquirer.xml',
        'data/mollie.xml',
    ],
    'installable': True,
    'currency': 'EUR',
    'images': ['images/main_screenshot.png']
}
