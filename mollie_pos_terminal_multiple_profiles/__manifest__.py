{
    "name": "Mollie POS Terminal Multiple Profiles",
    "version": "19.0.1.0.0",
    "summary": "Use a Mollie terminal API key per Point of Sale",
    "author": "Mollie",
    "maintainer": "Droggol Infotech Private Limited",
    "license": "LGPL-3",
    "category": "Point of Sale",
    "depends": ["mollie_pos_terminal", "point_of_sale"],
    "data": [
        "views/res_config_settings_views.xml",
        "wizard/mollie_sync_terminal.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "images": [
        "static/description/cover.png",
    ],
}
