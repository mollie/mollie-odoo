/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import { patch } from '@web/core/utils/patch';
import { patchDynamicContent } from '@web/public/utils';
import { PaymentForm } from '@payment/interactions/payment_form';
import { QrDialog } from '@payment_mollie_official/js/qr_dialog';
import { jsToPyLocale } from "@web/core/l10n/utils";


patch(PaymentForm.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            '.o_mollie_issuer': {
                't-on-click': this._onClickIssuer.bind(this),
            },
            'input[name="mollieCardType"]': {
                't-on-change': this._onChangeCardType.bind(this),
            },
        });
    },

    // /**
    //  * @override
    //  */
    async willStart() {
        // Show apple pay option only for apple devices
        if (!(window.ApplePaySession && window.ApplePaySession.canMakePayments())) {
            const applePayInput = this.el.querySelector('input[data-payment-method-code="apple_pay"]');
            if (applePayInput) {
                const parentLi = applePayInput.closest('li[name="o_payment_option"]');
                if (parentLi) {
                    parentLi.remove();
                }
            }
        }
        return await super.willStart();
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
            await super._prepareInlineForm(...arguments);
            return;
        }
        let creditCardContainer = this.el.querySelector("#o_mollie_component");
        if (!creditCardContainer || this.mollieComponentLoaded) {
            await super._prepareInlineForm(...arguments);
            return;
        }
        const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
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

        const mollieElem = this.el.querySelector('#o_mollie_component');
        const mollieInfo = mollieElem.dataset;
        const mollieProfileId = mollieInfo ? mollieInfo.profile_id : null;
        const mollieTestMode = mollieInfo ? mollieInfo.mode === 'test' : false;
        const lang = jsToPyLocale(document.documentElement.getAttribute("lang")) || 'en_US';
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
        let componentError = document.querySelector(`${componentId}-error`);
        component.addEventListener('change', function (ev) {
            if (!componentError) {
                return;
            }
            if (ev.error && ev.touched) {
                componentError.textContent = ev.error;
            } else {
                componentError.textContent = '';
            }
        });
    },

    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        let hasMollieCreditCardContainer = this.el.querySelector("#o_mollie_component");
        if (providerCode !== 'mollie' || paymentMethodCode !== 'card' || !hasMollieCreditCardContainer) {
            // Tokens are handled by the generic flow
            await super._initiatePaymentFlow(...arguments);
            return;
        }

        this._mollieCardToken = false;
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(checkedRadio);
        const useSavedCard = inlineForm.querySelector('#mollieSavedCard')?.checked;

        if (this.mollieComponentLoaded && !useSavedCard) {
            this._mollieCardToken = await this._prepareMollieCardToken();
        }

        if (!this._mollieCardToken && !useSavedCard) {
            return; // Error already displayed in _prepareMollieCardToken
        }
        await super._initiatePaymentFlow(...arguments);
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
        const transactionRouteParams = super._prepareTransactionRouteParams(...arguments);
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
        this.el.querySelector('#o_mollie_component').classList.toggle('d-none', $(ev.currentTarget).val() !== 'component');
        this.el.querySelector('#o_mollie_save_card').classList.toggle('d-none', $(ev.currentTarget).val() !== 'component');

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
            this.services.dialog.add(QrDialog, {
                qrImgSrc: qrImgSrc,
                submitRedirectForm: super._processRedirectFlow(...arguments),
            });
            this._enableButton();
        } else {
            return super._processRedirectFlow(...arguments);
        }
    },

});
