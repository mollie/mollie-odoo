/** @odoo-module **/

import Dialog from '@web/legacy/js/core/dialog';


const QrDialog = Dialog.extend({
    template: 'mollie.qr.dialog',
    events: {
        "click .dr_continue_checkout": '_onClickContinue',
    },
    /**
     * @override
     * @param {Object} options
     */
    init: function (parent, options) {
        options = options || {};
        this.rpc = this.bindService("rpc");
        this.qrImgSrc = options.qrImgSrc;
        this.submitRedirectForm = options.submitRedirectForm;
        this._super(parent, $.extend(true, {}, options));
    },

    /**
     * @override
     *
     * We start payment status poll from this method.
     *
     */
    start: function() {
        this._poll();
        return this._super.apply(this, arguments);
    },

    /**
     * @private
     *
     * This method recalls pall after few seconds
     *
     * Note:-
     * This is not optimal solution. websocket or long polling would be perfect solution.
     * But there is no proper way to manage it in odoo at the moment.
     * Odoo it self uses timeout based poll for payment.
     * See: https://github.com/odoo/odoo/blob/16.0/addons/payment/static/src/js/post_processing.js
    */
    _recallPolling: function () {
        setTimeout(this._poll.bind(this), 5000);
    },

    /**
     * @private
     *
     * This method make rpc to get status of transaction.
     * It will be redirected to the payment page, if the
     * transaction has status other than 'draft'.
     */
    _poll: function () {
        var self = this;
        this.rpc('/payment/status/poll', {
            'csrf_token': odoo.csrf_token,
        }).then(function(data) {
            if(data.success === true) {
                if (data.display_values_list.length > 0) {
                    if (data.display_values_list[0].state != 'draft') {
                        window.location = data.display_values_list[0].landing_route;
                        return;
                    }
                }
            }
            self._recallPolling();
        }).catch(error => {
            self._recallPolling();
        });
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {MouseEvent} ev
     *
     * This will submit the redirect form and resume the default payment flow
     */
    _onClickContinue: function (ev) {
        this.submitRedirectForm();
    }

});

export default QrDialog;
