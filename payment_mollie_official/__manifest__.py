# -*- coding: utf-8 -*-
{
    "name": "Mollie Payments",
    "version": "13.0.1",
    "author": "Mollie",
    "license": "LGPL-3",
    "website": "http://www.mollie.com",
    "category": "eCommerce",
    "description": """
        Mollie helps businesses of all sizes to sell and build
         more efficiently with a solid but easy-to-use payment solution.
         Start growing your business today with effortless payments.
    """,
    "depends": ["payment"],
    "data": [
        "data/payment_acquirer_data.xml",
        "data/ir_cron.xml",
        "data/method_data.xml",
        "security/ir.model.access.csv",
        "wizard/force_updates.xml",
        "wizard/config_mollie_view.xml",
        "views/provider_log.xml",
        "views/payment_views.xml",
        "views/payment_templates.xml",
        "views/assets.xml",
        "views/account_move_views.xml",
    ],
    "images": ["static/images/main_screenshot.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
}
