{
    'name': 'Mollie Subscription',
    'version': '1.0',
    'category': 'eCommerce',
    'license': 'LGPL-3',
    'summary': 'Mollie Subscription',
    'description': """Mollie Subscription""",
    'depends': ["payment_mollie_official", "website_sale_wishlist", "sale_management"],
    'data': [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/ir_sequence.xml",
        "views/product_views.xml",
        "views/partner_view.xml",
        "views/sale_order_view.xml",
        "views/templates.xml",
        "views/sale_portal_templates.xml",
        "views/mollie_subscription_view.xml",
        "views/mollie_payment_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "mollie_subscription_ept/static/src/js/cart.js",
            "mollie_subscription_ept/static/src/js/cancel_subscription.js",
        ],
    },
    "python_dependencies": ["mollie-api-python"],
}
