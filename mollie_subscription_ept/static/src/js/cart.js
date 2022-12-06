odoo.define('mollie_subscription_ept.clear_warn', function (require) {
    "use strict";
    $('#clear_warn_wishlist_btn').click(function () {
        var ajax = require('web.ajax');
        ajax.jsonRpc("/clear_warn", 'call', {'hide_warn':true}).then(function(data) {
        if (data) {} else {}});
    });

    $('#clear_warn_in_cart_btn').click(function () {
        var ajax = require('web.ajax');
        ajax.jsonRpc("/clear_warn", 'call', {'hide_warn':true}).then(function(data) {
        if (data) {} else {}});
    });
});
