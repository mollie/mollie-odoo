/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { Dialog } from '@web/core/dialog/dialog';
import { Component, onWillStart, onWillDestroy } from '@odoo/owl';
import { _t } from "@web/core/l10n/translation";


export class QrDialog extends Component {
    static template = "payment_mollie_official.QrDialog";

    static components = { Dialog };

    static props = {
        qrImgSrc: { type: String },
        submitRedirectForm: Function,
        size: { type: String, optional: true },
        title: { type: String, optional: true },
    };

    static defaultProps = {
        size: "sm",
        title: _t("Scan QR"),
    };

    /**
     * @override
     *
     * We start payment status poll from this method.
     *
     */
    setup() {
        onWillStart(() => this._poll());
        onWillDestroy(() => clearTimeout(this.pollTimeout));

    }

    /**
     * @private
     *
     * This method recalls call after few seconds
     *
     * Note:-
     * This is not optimal solution. websocket or long polling would be perfect solution.
     * But there is no proper way to manage it in odoo at the moment.
     * Odoo it self uses timeout based poll for payment.
     * See: https://github.com/odoo/odoo/blob/18.0/addons/payment/static/src/js/post_processing.js
    */
    _recallPolling() {
        this.pollTimeout = setTimeout(this._poll.bind(this), 5000);
    }

    /**
     * @private
     *
     * This method make rpc to get status of transaction.
     * It will be redirected to the payment page, if the
     * transaction has status other than 'draft'.
     */
    _poll() {
        var self = this;
        rpc('/payment/status/poll', {
        'csrf_token': odoo.csrf_token,
        }).then(data => {
            if (data.success === true) {
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
    }

    /**
     * This will submit the redirect form and resume the default payment flow
     */
    onClickContinue() {
        this.props.submitRedirectForm();
    }

}
