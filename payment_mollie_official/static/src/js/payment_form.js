/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import paymentForm from '@payment/js/payment_form';
import QrDialog from '@payment_mollie_official/js/qr_dialog';

paymentForm.include({

    events: Object.assign({}, paymentForm.prototype.events, {
        'click .o_mollie_issuer': '_onClickIssuer',
        'change input[name="mollieCardType"]': '_onChangeCardType',
    }),

    /**
     * @override
     */
    start: function () {
        // Show apple pay option only for apple devices
        if (!(window.ApplePaySession && window.ApplePaySession.canMakePayments())) {
            this.$('input[data-payment-method-code="apple_pay"]').closest('li[name="o_payment_option"]').remove();
        }
        return this._super.apply(this, arguments);
    },

    /**
     * Update the payment context to set the flow to 'direct'.
     *
     * @override method from @payment/js/payment_form
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'mollie' || paymentMethodCode !== 'card') {
            this._super(...arguments);
            return;
        }
        let $creditCardContainer = this.$("#o_mollie_component");
        if (!$creditCardContainer.length || this.mollieComponentLoaded) {
            return this._super(...arguments);
        }
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(checkedRadio);
        const useSavedCard = inlineForm.querySelector('#mollieSavedCard')?.checked;
        if (!useSavedCard) {
            await this._setupMollieComponent();
        }
    },

    /**
     * Setup the mollie component for the credit card from.
    *
    * @private
    */
    async _setupMollieComponent() {
        this.mollieComponentLoaded = true;
        await loadJS('https://js.mollie.com/v1/mollie.js');

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

    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        this._mollieCardToken = false;
        const _super = this._super.bind(this);

        // TODO: put next 3 lines function (it keeps repeating)
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(checkedRadio);
        const useSavedCard = inlineForm.querySelector('#mollieSavedCard')?.checked;

        if (providerCode === 'mollie' && paymentMethodCode === 'card' && this.mollieComponentLoaded && !useSavedCard) {
            this._mollieCardToken = await this._prepareMollieCardToken();
            // TODO: What if there no token
        }
        await _super(...arguments);
        return;
    },

    /**
     * Create the card token from the mollieComponent.
     *
     * @private
     * @return {Promise}
     */
    async _prepareMollieCardToken() {
        let tokenResult = await this.mollieComponent.createToken()
        if (tokenResult.error) {
            this._displayErrorDialog(
                _t("Error"), tokenResult.error.message
            );
            this._enableButton();
        }
        return tokenResult.token || false;
    },
    // /**
    //  * Prepare the params for the RPC to the transaction route.
    //  *
    //  * @private
    //  * @return {object} The transaction route params.
    //  */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = this._super(...arguments);
        const paymentContext = this.paymentContext;
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(checkedRadio);

        if (paymentContext.providerCode === 'mollie') {

            if (paymentContext.paymentMethodCode === 'card') {
                const useSavedCard = inlineForm.querySelector('#mollieSavedCard')?.checked;

                if(this._mollieCardToken && !useSavedCard) {
                    transactionRouteParams['mollie_card_token'] = this._mollieCardToken;
                }

                if (inlineForm.querySelector('input[name="o_mollie_save_card"]') || useSavedCard) {
                    transactionRouteParams['mollie_save_card'] = inlineForm.querySelector('input[name="o_mollie_save_card"]').checked || useSavedCard;
                }

            }
            const activeIssuer = inlineForm.querySelector('.o_mollie_issuer.active')
            if (activeIssuer) {
                transactionRouteParams['mollie_payment_issuer'] = inlineForm.querySelector('.o_mollie_issuer.active').dataset.mollieIssuer;
            }

        }

        return transactionRouteParams;
    },

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

        if ($(ev.currentTarget).val() == 'component' && !this.mollieComponentLoaded) {
            this._setupMollieComponent();
        }
    },

    /**
     * Redirect the customer by submitting the redirect form included in the processing values.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    _processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        const $redirectForm = $(processingValues.redirect_form_html).attr(
            'id', 'o_payment_redirect_form'
        );
        var qrImgSrc = $redirectForm.data('qrsrc');
        if (qrImgSrc) {
            var dialog = new QrDialog(this, {
                qrImgSrc: qrImgSrc,
                submitRedirectForm: this._super.bind(this, ...arguments),
                size: 'small',
                title: _t('Scan QR'),
                renderFooter: false
            });
            dialog.opened().then(() => {
                this._enableButton();
            });
            dialog.open();
        } else {
            return this._super(...arguments);
        }
    },

});
