# -*- coding: utf-8 -*-
{
    'name': 'Mollie Payment Acquirer',
    'version': '1.10',
    'author': 'Mollie & BeOpen',
    'website': 'http://www.mollie.com',
    'category': 'eCommerce',
    'description': """
        Mollie helps businesses of all sizes to sell and build
         more efficiently with a solid but easy-to-use payment solution.
         Start growing your business today with effortless payments.
    """,
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
