/* global Mollie */
odoo.define('mollie.payment.form', function (require) {
"use strict";

    const ajax = require('web.ajax');
    const checkoutForm = require('payment.checkout_form');
    const core = require('web.core');
    const qrDialog = require('mollie.qr.dialog');
    const { loadJS } = require('@web/core/assets');

    const _t = core._t;

    checkoutForm.include({
        events: _.extend({
            'click .o_mollie_issuer': '_onClickIssuer',
            'change input[name="mollieCardType"]': '_onChangeCardType',
        }, checkoutForm.prototype.events),

        /**
         * @override
         */
        start: function () {
            this.mollieComponentLoaded = false;
            // Show apple pay option only for apple devices
            if (window.ApplePaySession && window.ApplePaySession.canMakePayments()) {
                this.$('input[data-mollie-method="applepay"]').closest('.o_payment_option_card').removeClass('d-none');
            }
            return this._super.apply(this, arguments);
        },

        /**
        *  Create the mollie component  and bind events to handles errors.
        *
        * @private
        * @param {string} type - component type
        * @param {string} componentId - Id of component to bind the listener
        */
        _createMollieComponent: function (type, componentId) {
            let component = this.mollieComponent.createComponent(type);
            component.mount(componentId);

            let $componentError = this.$(`${componentId}-error`);
            component.addEventListener('change', function (ev) {
                if (ev.error && ev.touched) {
                    $componentError.text(ev.error);
                } else {
                    $componentError.text('');
                }
            });
        },

        /**
         * Prepare the inline form of mollie for direct payment.
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} code - The provider of the selected payment option's provider
         * @param {number} paymentOptionId - The id of the selected payment option
         * @param {string} flow - The online payment flow of the selected payment option
         * @return {Promise}
         */
        _prepareInlineForm: function (code, paymentOptionId, flow) {
            if (code !== 'mollie') {
                return this._super(...arguments);
            }
            // this._setPaymentFlow('direct');
            let $creditCardContainer = this.$(`#o_payment_mollie_method_inline_form_${paymentOptionId} #o_mollie_component`);
            if (!$creditCardContainer.length || this.mollieComponentLoaded) {
                return this._super(...arguments);
            }
            return loadJS("https://js.mollie.com/v1/mollie.js").then(() => this._setupMollieComponent());
        },

        /**
         * Create the card token from the mollieComponent.
         *
         * @private
         * @return {Promise}
         */
        _prepareMollieCardToken: function () {
            return this.mollieComponent.createToken().then(result => {
                if (result.error) {
                    this.displayNotification({
                        type: 'danger',
                        title: _t("Error"),
                        message: result.error.message,
                        sticky: false,
                    });
                    this._enableButton();
                    $.unblockUI();
                }
                return result.token || false;
            });
        },

        /**
         * Add mollie specific params to the transaction route params
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} code - The provider of the selected payment option's provider
         * @param {number} paymentOptionId - The id of the selected payment option
         * @param {string} flow - The online payment flow of the selected payment option
         * @return {object} The extended transaction route params
         */
        _prepareTransactionRouteParams: function (code, paymentOptionId, flow) {
            const transactionRouteParams = this._super(...arguments);
            if (code !== 'mollie') {
                return transactionRouteParams;
            }
            const $checkedRadios = this.$('input[name="o_payment_radio"]:checked');
            const mollie_method = $checkedRadios.data('mollie-method');
            let mollieData = {
                mollie_method: $checkedRadios.data('mollie-method'),
                payment_option_id: $checkedRadios.data('mollie-provider-id'),
            };

            const useSavedCard = $('#mollieSavedCard').prop('checked');
            if (this.cardToken && !useSavedCard) {
                mollieData['mollie_card_token'] = this.cardToken;
            }

            if (mollie_method === 'creditcard' && (this.$('#o_mollie_save_card').length || useSavedCard)) {
                mollieData['mollie_save_card'] = this.$('#o_mollie_save_card input').prop("checked") || useSavedCard;
            }

            if ($checkedRadios.data('mollie-issuers')) {
                mollieData['mollie_issuer'] = this.$(`#o_payment_mollie_method_inline_form_${paymentOptionId} .o_mollie_issuer.active`).data('mollie-issuer');
            }
            return {...transactionRouteParams, ...mollieData};
        },

        /**
         * Manage mollie payment transaction route response.
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} code - The provider of the provider
         * @param {number} providerId - The id of the provider handling the transaction
         * @param {object} processingValues - The processing values of the transaction
         * @return {Promise}
         */
        _processDirectPayment: function (code, providerId, processingValues) {
            if (code !== 'mollie') {
                return this._super(...arguments);
            }
            window.location = processingValues.redirect_url;
        },

        /**
         * Submit the data to transactionRoute and generate card token if needed.
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} code - The provider of the payment option's provider
         * @param {number} paymentOptionId - The id of the payment option handling the transaction
         * @param {string} flow - The online payment flow of the transaction
         * @return {Promise}
         */
        _processPayment: function (code, paymentOptionId, flow) {
            if (code !== 'mollie') {
                return this._super(...arguments);
            }
            this.cardToken = false;
            const creditCardChecked = this.$('input[data-mollie-method="creditcard"]:checked').length == 1;
            const useSavedCard = $('#mollieSavedCard').prop('checked');
            if (creditCardChecked && this.$('#o_mollie_component').length && !useSavedCard) {
                const _super = this._super.bind(this, ...arguments);
                return this._prepareMollieCardToken()
                    .then((cardToken) => {
                        if (cardToken) {
                            this.cardToken = cardToken;
                            return _super();
                        }
                    });
            } else {
                return this._super(...arguments);
            }
        },

        /**
         * Redirect the customer by submitting the redirect form included in the processing values.
         *
         * We have overridden this method to show qr code popup.
         *
         * @override
         * @param {string} code - The provider of the provider
         * @param {number} providerId - The id of the provider handling the transaction
         * @param {object} processingValues - The processing values of the transaction
         * @return {undefined}
         */
        _processRedirectPayment: function(code, providerId, processingValues) {
            const $redirectForm = $(processingValues.redirect_form_html).attr(
                'id', 'o_payment_redirect_form'
            );
            var qrImgSrc = $redirectForm.data('qrsrc');
            if (qrImgSrc) {
                var dialog = new qrDialog(this, {
                    qrImgSrc: qrImgSrc,
                    submitRedirectForm: this._super.bind(this, ...arguments),
                    size: 'small',
                    title: _t('Scan QR'),
                    renderFooter: false
                });
                dialog.opened().then(() => {
                    $.unblockUI();
                    this._enableButton();
                });
                dialog.open();
            } else {
                return this._super(...arguments);
            }
        },

        /**
        * Setup the mollie component for the credit card from.
        *
        * @private
        */
        _setupMollieComponent: function () {

            const mollieProfileId = this.$('#o_mollie_component').data('profile_id');
            const mollieTestMode = this.$('#o_mollie_component').data('mode') === 'test';

            let context;
            this.trigger_up('context_get', {
                callback: function (ctx) {
                    context = ctx;
                },
            });
            const lang = context.lang || 'en_US';
            this.mollieComponent = Mollie(mollieProfileId, { locale: lang, testmode: mollieTestMode });
            this._createMollieComponent('cardHolder', '#mollie-card-holder');
            this._createMollieComponent('cardNumber', '#mollie-card-number');
            this._createMollieComponent('expiryDate', '#mollie-expiry-date');
            this._createMollieComponent('verificationCode', '#mollie-verification-code');
            this.mollieComponentLoaded = true;
        },

        //--------------------------------------------------------------------------
        // Handlers
        //--------------------------------------------------------------------------

        /**
         * @private
         * @param {MouseEvent} ev
         */
        _onClickIssuer: function (ev) {
            let $container = $(ev.currentTarget).closest('.o_mollie_issuer_container');
            $container.find('.o_mollie_issuer').removeClass('active border-primary');
            $(ev.currentTarget).addClass('active border-primary');
        },
        /**
         * @private
         * @param {MouseEvent} ev
         */
        _onChangeCardType: function (ev) {
            this.$('#o_mollie_component').toggleClass('d-none', $(ev.currentTarget).val() !== 'component');
            this.$('#o_mollie_save_card').toggleClass('d-none', $(ev.currentTarget).val() !== 'component');
        },
    });

});