# -*- encoding: utf-8 -*-
{
    'name': 'Mollie Payment Acquirer',
    'version': '1.11',
    'author': 'Mollie & BeOpen',
    'website': 'http://www.mollie.com',
    'category': 'eCommerce',
    'description': "",
    'depends': ['payment','website_sale'],
    'data': [
        'views/payment_mollie_templates.xml',
        'views/payment_views.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'images': ['images/main_screenshot.png']
}
