odoo.define('mollie_subscription_ept.cancel_subscriptions', function(require){
"use strict";

    $(document).ready(function() {
        var rpc = require('web.rpc');

        $('#cancel_subscription_btn').click(function () {
            $('#cancel_subscription_modal').modal('show')
        });

        $('#cancel_subscription').click(function () {
            var sub_id = $('#subscriptions_id').val()
            var res = rpc.query({
                model: 'mollie.subscription',
                method: 'cancel_subscription',
                kwargs: {'sub_id': sub_id},
                args: [[]]
            }).then(function () {
                window.location.reload()
            });
        });
    });
});