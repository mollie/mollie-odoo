odoo.define('mollie_subscription.website_sale_utils', function (require) {
'use strict';

const wsUtils = require('website_sale.utils');
const cartHandlerMixin = {
    _addToCartInPage(params) {
        params.force_create = true;
        return this._rpc({
            route: "/shop/cart/update_json",
            params: params,
        }).then(async data => {
            if (data.cart_quantity && (data.cart_quantity !== parseInt($(".my_cart_quantity").text()))) {
                await wsUtils.animateClone($('header .o_wsale_my_cart').first(), this.$itemImgContainer, 25, 40);
                wsUtils.updateCartNavBar(data);
            }
            if (data.show_in_cart_warning)
            {
               wsUtils.showWarning('Important Notice:It is not possible to make a purchase that includes both a subscription and a regular product simultaneously.Please purchase these separately.');
            }
        });
    },
};

wsUtils.cartHandlerMixin = {
    ...wsUtils.cartHandlerMixin,
    ...cartHandlerMixin
};
});
