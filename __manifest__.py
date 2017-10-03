# -*- encoding: utf-8 -*-
{
    'name': 'Mollie acquirer for online payments',
    'version': '1.10',
    'author': 'BeOpen NV',
    'website': 'http://www.beopen.be',
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
