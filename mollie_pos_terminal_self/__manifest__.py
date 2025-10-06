{
    'name': 'Mollie Pos Terminal Kiosk (self order)',
    'version': '18.0.0.0',
    'summary': "Addon for the self order app that allows customers to pay by Mollie terminal.",
    'author': 'Mollie',
    'category': 'Point of Sale',
    'maintainer': 'Droggol Infotech Private Limited',
    'license': 'LGPL-3',
    'auto_install': True,
    'depends': [
        'mollie_pos_terminal', 'pos_self_order'
    ],
    'images': [
        'static/description/cover.png',
    ],
    'assets': {
        'pos_self_order.assets': [
            'mollie_pos_terminal_self/static/src/app/self_order_service.js',
        ]
    }
}


# error from
# /home/droggol/odoo/community/addons/pos_self_order/static/src/app/self_order_service.js line: 709
# updateOrderFromServer(order) {
#     this.currentOrder.updateDataFromServer(order);
# }
# 'updateDataFromServer' method not found
