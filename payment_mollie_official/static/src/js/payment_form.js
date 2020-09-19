odoo.define('mollie.payment.form', function (require) {
"use strict";

var payement_form = require('payment.payment_form')

var core = require('web.core');
var Dialog = require('web.Dialog');
var publicWidget = require('web.public.widget');
var ajax = require('web.ajax');

var _t = core._t;

// Override payment form for mollie's custom flow
publicWidget.registry.PaymentForm.include({
    events: _.extend({
        'click .o_issuer': '_clickIssuer',
    }, publicWidget.registry.PaymentForm.prototype.events),
    /**
     * @override
     */
    init: function () {
        this.mollie_loaded = false;
        this.mollieJSURL = "https://js.mollie.com/v1/mollie.js";
        return this._super.apply(this, arguments);
    },

    /**
     * @override
     */
    willStart: function () {
        var self = this;
        self.libPromise = ajax.loadJS(self.mollieJSURL);
        return this._super.apply(this, arguments).then(function () {
            return self.libPromise;
        });
    },

    // ---------------------------------
    // Existing Overridden methods
    // ---------------------------------

    /**
     * @override
     */
    updateNewPaymentDisplayStatus: function () {
        var self = this;
        var $checkedRadio = this.$('input[type="radio"]:checked');
        if ($checkedRadio.length !== 1) {
            return;
        }
        var response = this._super.apply(this, arguments);
        var provider = $checkedRadio.data('provider');
        var methodName = $checkedRadio.data('methodname');
        if (provider === 'mollie' && (methodName === 'creditcard' || methodName === 'ideal')) {
            this.$('[id*="o_payment_add_token_acq_"]').addClass('d-none');
            this.$('[id*="o_payment_form_acq_"]').addClass('d-none');
            this.$('#o_payment_form_acq_' + methodName).removeClass('d-none');

            // Wait js lad for creditcard
            if (!this.mollie_loaded && methodName === 'creditcard') {
                this.mollie_loaded = true;
                // Wait for lib in case network is slow
                self.libPromise.then(function () {
                    self._loadMollieComponent();
                });
            }
        }

        return response;

    },
    /**
     * @override
     */
    payEvent: function (ev) {
        ev.preventDefault();
        var form = this.el;
        var self = this;

        if (ev.type === 'submit') {
            var button = $(ev.target).find('*[type="submit"]')[0]
        } else {
            var button = ev.target;
        }

        var $checkedRadio = this.$('input[type="radio"]:checked');
        if ($checkedRadio.length === 1 && $checkedRadio.data('provider') === 'mollie') {
            // Right now pass and submit the from to get mollie component token.
            this.disableButton(button);
            var methodName = $checkedRadio.data('methodname');
            if (methodName === 'creditcard') {
                return this._getMollieToken(button)
                    .then(this._createMollieTransaction.bind(this, methodName, button));
            } else {
                return this._createMollieTransaction(methodName, button);
            }
        } else {
            return this._super.apply(this, arguments);
        }
    },

    // ---------------------------------
    // Mollie specific methods
    // ---------------------------------

    /**
     * Called when clicking on mollie radio button
     * This will setup mollie component
     *
     * @private
     */
    _loadMollieComponent: function () {
        var mollieProfileId = this.$('#o_mollie_component').data('profile_id');
        var mollieTestMode = this.$('#o_mollie_component').data('mode') === 'test';
        this.mollieComponent = Mollie(mollieProfileId, { locale: 'en_US', testmode: mollieTestMode });
        this._bindMollieInputs();
    },
    /**
     * @private
     */
    _getMollieToken: function (button) {
        var self = this;
        return this.mollieComponent.createToken().then(function (result) {
            if (result.error) {
                self.displayNotification({
                    type: 'danger',
                    title: _t("Error"),
                    message: result.error.message,
                    sticky: false,
                });
                self.enableButton(button);
            }
            return result.token || false;
        });
    },
    /**
     * @private
     */
    _createMollieTransaction: function (paymentmethod, button, token) {
        if (!token && paymentmethod === 'creditcard') {
            return;
        }
        var self = this;
        var issuer = false;
        var checked_radio = this.$('input[type="radio"]:checked')[0];
        var acquirer_id = this.getAcquirerIdFromRadio(checked_radio);
        var $tx_url = this.$el.find('input[name="prepare_tx_url"]');
        if (paymentmethod === 'ideal') {
            issuer = this.$('#o_payment_form_acq_ideal .o_issuer.active').data('methodname');
        }

        if ($tx_url.length === 1) {
            return this._rpc({
                route: $tx_url[0].value,
                params: {
                    'acquirer_id': parseInt(acquirer_id),
                    'save_token': false,
                    'access_token': this.options.accessToken,
                    'success_url': this.options.successUrl,
                    'error_url': this.options.errorUrl,
                    'callback_method': this.options.callbackMethod,
                    'order_id': this.options.orderId,
                    'mollie_payment_token': token,
                    'paymentmethod': paymentmethod,
                    'mollie_issuer': issuer
                },
            }).then(function (result) {
                if (result) {
                    // if the server sent us the html form, we create a form element
                    var newForm = document.createElement('form');
                    newForm.setAttribute("method", "post"); // set it to post
                    newForm.setAttribute("provider", checked_radio.dataset.provider);
                    newForm.hidden = true; // hide it
                    newForm.innerHTML = result; // put the html sent by the server inside the form
                    var action_url = $(newForm).find('input[name="data_set"]').data('actionUrl');
                    newForm.setAttribute("action", action_url); // set the action url
                    $(document.getElementsByTagName('body')[0]).append(newForm); // append the form to the body
                    $(newForm).find('input[data-remove-me]').remove(); // remove all the input that should be removed
                    var errorInput = $(newForm).find("input[name='error_msg']"); // error message
                    if (errorInput && errorInput.val()) {
                        var msg = _t('Payment method is not supported. Try another payment method or contact us');
                        var errorMsg = (errorInput.val() || "");
                        new Dialog(null, {
                            title: _t('Info'),
                            size: 'medium',
                            $content: _.str.sprintf('<p><b><b> %s </b> <br/> <span class="small text-muted"> Error Message: %s </span> </p>', msg, errorMsg),
                            buttons: [
                                { text: _t('Ok'), close: true }]
                        }).open();
                        self.enableButton(button);
                        return new Promise(function () { });
                    }

                    if (action_url) {
                        newForm.submit(); // and finally submit the form
                        return new Promise(function () { });
                    }
                }
                else {
                    self.displayError(
                        _t('Server Error'),
                        _t("We are not able to redirect you to the payment form.")
                    );
                    self.enableButton(button);
                }
            }).guardedCatch(function (error) {
                error.event.preventDefault();
                self.displayError(
                    _t('Server Error'),
                    _t("We are not able to redirect you to the payment form.") + " " +
                    self._parseError(error)
                );
            });
        }
        else {
            // we append the form to the body and send it.
            this.displayError(
                _t("Cannot setup the payment"),
                _t("We're unable to process your payment.")
            );
            self.enableButton(button);
        }
    },
    /**
     * @private
     */
    _bindMollieInputs: function () {
        var cardHolder = this.mollieComponent.createComponent('cardHolder');
        cardHolder.mount('#mollie-card-holder');

        var cardNumber = this.mollieComponent.createComponent('cardNumber');
        cardNumber.mount('#mollie-card-number');

        var expiryDate = this.mollieComponent.createComponent('expiryDate');
        expiryDate.mount('#mollie-expiry-date');

        var verificationCode = this.mollieComponent.createComponent('verificationCode');
        verificationCode.mount('#mollie-verification-code');

        // Validation
        var cardHolderError = this.$('#mollie-card-holder-error')[0];
        cardHolder.addEventListener('change', function (ev) {
            if (ev.error && ev.touched) {
                cardHolderError.textContent = ev.error;
            } else {
                cardHolderError.textContent = '';
            }
        });

        var cardNumberError = this.$('#mollie-card-number-error')[0];
        cardNumber.addEventListener('change', function (ev) {
            if (ev.error && ev.touched) {
                cardNumberError.textContent = ev.error;
            } else {
                cardNumberError.textContent = '';
            }
        });

        var expiryDateError = this.$('#mollie-expiry-date-error')[0];
        expiryDate.addEventListener('change', function (ev) {
            if (ev.error && ev.touched) {
                expiryDateError.textContent = ev.error;
            } else {
                expiryDateError.textContent = '';
            }
        });

        var verificationCodeError = this.$('#mollie-verification-code-error')[0];
        verificationCode.addEventListener('change', function (ev) {
            if (ev.error && ev.touched) {
                verificationCodeError.textContent = ev.error;
            } else {
                verificationCodeError.textContent = '';
            }
        });
    },

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /**
     * @private
     * @param {MouseEvent} ev
     */
    _clickIssuer: function (ev) {
        var $container = $(ev.currentTarget).closest('.o_issuer_container');
        $container.find('.o_issuer').removeClass('active');
        $(ev.currentTarget).addClass('active');
    }

});

});
