# -*- coding: utf-8 -*-

import requests
import base64
import logging

from odoo.http import request
from odoo import fields, models, Command, api
from odoo.addons.payment_mollie_official import const

_logger = logging.getLogger(__name__)


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    mollie_voucher_ids = fields.One2many('mollie.voucher.line', 'method_id', string='Mollie Voucher Config')
    mollie_enable_qr_payment = fields.Boolean(string="Enable QR payment")
    mollie_has_issuers = fields.Boolean(string="Has mollie issuers")

    journal_id = fields.Many2one(
        'account.journal', string="Journal",
        compute='_compute_journal_id', inverse='_inverse_journal_id',
        domain="[('type', '=', 'bank')]")

    def _compute_journal_id(self):
        for mollie_method in self:
            provider = mollie_method.provider_ids[:1]
            if not provider or provider._get_code() != 'mollie':
                mollie_method.journal_id = False
                continue
            payment_method = self.env['account.payment.method.line'].search([
                ('code', '=', mollie_method._get_journal_method_code()),
            ], limit=1)
            if payment_method:
                mollie_method.journal_id = payment_method.journal_id
            else:
                mollie_method.journal_id = False

    def _inverse_journal_id(self):
        for mollie_method in self:
            provider = mollie_method.provider_ids[:1]
            if not provider or provider._get_code() != 'mollie':
                continue

            code = mollie_method._get_journal_method_code()
            payment_method_line = self.env['account.payment.method.line'].search([
                *self.env['account.payment.method.line']._check_company_domain(provider.company_id),
                ('code', '=', code),
            ], limit=1)

            if mollie_method.journal_id:
                if not payment_method_line:
                    self._link_mollie_payment_method_to_journal(mollie_method)
                else:
                    payment_method_line.journal_id = mollie_method.journal_id
            elif payment_method_line:
                payment_method_line.unlink()

    """ TODO: make this compute """
    def _get_journal_method_code(self):
        self.ensure_one()
        return f'mollie_{self.code}'

    def _link_mollie_payment_method_to_journal(self, mollie_method):
        provider = mollie_method.provider_ids[:1]
        default_payment_method_id = mollie_method._get_default_mollie_payment_method_id(mollie_method)
        existing_payment_method_line = self.env['account.payment.method.line'].search([
            *self.env['account.payment.method.line']._check_company_domain(provider.company_id),
            ('payment_method_id', '=', default_payment_method_id),
            ('journal_id', '=', mollie_method.journal_id.id)
        ], limit=1)

        if not existing_payment_method_line:
            self.env['account.payment.method.line'].create({
                'payment_method_id': default_payment_method_id,
                'journal_id': mollie_method.journal_id.id,
            })

    @api.model
    def _get_default_mollie_payment_method_id(self, mollie_method):
        provider_payment_method = self._get_provider_payment_method(mollie_method._get_journal_method_code())
        if not provider_payment_method:
            provider_payment_method = self.env['account.payment.method'].sudo().create({
                'name': f'Mollie {mollie_method.name}',
                'code': mollie_method._get_journal_method_code(),
                'payment_type': 'inbound',
            })
        return provider_payment_method.id

    @api.model
    def _get_provider_payment_method(self, code):
        return self.env['account.payment.method'].search([('code', '=', code)], limit=1)

    def _get_compatible_payment_methods(
        self, provider_ids, partner_id, currency_id=None, force_tokenization=False,
        is_express_checkout=False, **kwargs
    ):
        """ Search and return the payment methods matching the compatibility criteria.

        @override

        We override this because we do not want to filter methods based on odoo's conditions.
        We will filter them based mollie's compatibility via method's API.

        """

        result_pms = super()._get_compatible_payment_methods(
            provider_ids, partner_id, currency_id=currency_id, force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout, **kwargs
        )

        if not provider_ids:
            return result_pms

        # all active mollie methods from provider
        mollie_providers = self.env['payment.provider'].browse(provider_ids).filtered(lambda provider: provider._get_code() == 'mollie')
        mollie_active_pms = mollie_providers.mapped('payment_method_ids')

        if not mollie_providers:
            return result_pms

        def is_mollie_method(method):
            return method.provider_ids.filtered(lambda p: p.id in provider_ids)[:1]._get_code() == 'mollie'

        # mollie methods from super
        mollie_result_pms = result_pms.filtered(lambda m: is_mollie_method(m))
        non_mollie_pms = result_pms - mollie_result_pms

        # mollie methods from which we need to filter via method api
        mollie_allowed_methods = mollie_active_pms - non_mollie_pms

        # Fetch allowed methods via API
        has_voucher_line, extra_params = False, {'includeWallets': 'applepay'}

        is_partial_payment = False

        if kwargs.get('sale_order_id'):
            order_sudo = self.env['sale.order'].browse(kwargs['sale_order_id']).sudo()

            # payment_amount attribute is sent when user is paying via payment links. In that case payment amount is different than order amount.
            payment_amount = float(request.params.get('amount')) if request.params.get('amount') else False
            extra_params['amount'] = {'value': "%.2f" % (payment_amount or order_sudo.amount_total), 'currency': order_sudo.currency_id.name}

            if order_sudo.partner_invoice_id.country_id:
                extra_params['billingCountry'] = order_sudo.partner_invoice_id.country_id.code

            # ------------------ Check for partial payment ------------------


            # amount_selection attribute is sent when user use downpayment option to pay partial amount.
            is_downpayment = False

            # if payment_amount is that means it is payment link or partial payment via downpayment option
            if payment_amount:
                if payment_amount < order_sudo.amount_total:
                    is_partial_payment = True

            # sent when downpayent option manually selected in portal
            downpayment_selection = request.params.get('downpayment') if request else None
            if downpayment_selection == 'true':
                is_downpayment = True
                is_partial_payment = True
            elif downpayment_selection == 'false' and payment_amount != order_sudo.amount_total:
                extra_params['amount'] = {'value': "%.2f" % (order_sudo.amount_total), 'currency': order_sudo.currency_id.name} # reset payment amount to full amount
                is_partial_payment = False

            # Default case for partial payment (when portal page is loaded first time)
            needs_prepayment = order_sudo.prepayment_percent and order_sudo.prepayment_percent != 1.0
            if not payment_amount and not downpayment_selection and needs_prepayment:
                is_partial_payment = True
                is_downpayment = True

            has_voucher_line = order_sudo.mapped('order_line.product_id.product_tmpl_id')._get_mollie_voucher_category()

            if is_downpayment:
                extra_params['amount'] = {'value': "%.2f" % order_sudo._get_prepayment_required_amount(), 'currency': order_sudo.currency_id.name}

        if not kwargs.get('sale_order_id') and request and request.params.get('invoice_id'):
            invoice_id = request.params.get('invoice_id')
            invoice = self.env['account.move'].sudo().browse(int(invoice_id))
            amount_payment_link = float(request.params.get('amount', '0'))  # for payment links
            if invoice.exists():
                extra_params['amount'] = {'value': "%.2f" % (amount_payment_link or invoice.amount_residual), 'currency': invoice.currency_id.name}
                if invoice.partner_id.country_id:
                    extra_params['billingCountry'] = invoice.partner_id.country_id.code
                if (amount_payment_link and invoice.amount_total != amount_payment_link) or invoice.amount_total != invoice.amount_residual:
                    is_partial_payment = True

        partner = self.env['res.partner'].browse(partner_id)
        if not extra_params.get('billingCountry') and partner.country_id:
            extra_params['billingCountry'] = partner.country_id.code

        if has_voucher_line:
            extra_params['orderLineCategories'] = ','.join(has_voucher_line)
        else:
            mollie_allowed_methods = mollie_allowed_methods.filtered(lambda m: m.code != 'voucher')

        # Hide methods if mollie does not supports them (checks via api call)
        supported_methods = mollie_providers[:1]._api_mollie_get_active_payment_methods(extra_params=extra_params)  # sudo as public user do not have access to keys
        mollie_allowed_methods = mollie_allowed_methods.filtered(
            lambda m: (
                const.PAYMENT_METHODS_MAPPING.get(m.code, m.code) in supported_methods.keys() and
                (not is_partial_payment or (is_partial_payment and m.code not in const.NON_PARTIAL_PAYMENT_METHODS))
            )
        )
        mollie_issuers = {}
        for method, method_data in supported_methods.items():
            issuers = method_data.get('issuers')
            if issuers:
                mollie_method = self.search([('code', '=', method), ('primary_payment_method_id', '=', False)])
                if mollie_method:
                    issuers_codes = list(map(lambda issuer: issuer['id'], issuers))
                    mollie_issuers[mollie_method[0].id] = mollie_method[0].brand_ids.filtered(lambda brand: brand.active and brand.code in issuers_codes).ids  # always use first method, didn't occuer any case to get multiple methods but handle it

        return (non_mollie_pms | mollie_allowed_methods).with_context(mollie_issuers=mollie_issuers)

    def _get_mollie_method_supported_issuers(self):
        mollie_issuers = self.env.context.get('mollie_issuers', [])
        if mollie_issuers.get(self.id):
            return self.browse(mollie_issuers[self.id])
        return []

    def _get_inline_form_xml_id(self, original_xml_id, provider_sudo):
        self.ensure_one()
        inline_form_xml_id = original_xml_id
        if provider_sudo._get_code() == 'mollie':
            # TODO: map word creditcard with PAYMENT_METHODS_MAPPING
            if self.code == 'card' and (provider_sudo.mollie_use_components or provider_sudo.mollie_show_save_card):    # inline card
                inline_form_xml_id = 'payment_mollie_official.mollie_creditcard_component'
            elif self.mollie_has_issuers and self.code != 'ideal':  # Issuers is removed for ideal as mollie does not support issuers anymore
                inline_form_xml_id = 'payment_mollie_official.mollie_issuers_list'
        return inline_form_xml_id

    def _sync_mollie_methods(self, mollie_provider):
        """ Create/Update the mollie payment methods based on configuration
            in the mollie.com. This will automatically activate/deactivate methods
            based on your configurateion on the mollie.com

            :param dict methods_data: Mollie's method data received from api
        """

        mollie_methods_data = mollie_provider._api_mollie_get_active_payment_methods(all_methods=True)
        all_methods = self.with_context(active_test=False).search([('is_primary', '=', True)])

        # update_the_mapping
        for odoo_method_code, mollie_method_code in const.PAYMENT_METHODS_MAPPING.items():
            if mollie_methods_data.get(mollie_method_code):
                mollie_methods_data[odoo_method_code] = mollie_methods_data.pop(mollie_method_code)

        # Create new methods if needed
        methods_to_create = mollie_methods_data.keys() - set(all_methods.mapped('code'))
        for method in methods_to_create:
            method_info = mollie_methods_data[method]
            self.create({
                'name': method_info['description'],
                'code': method_info['id'],
                'active': False,
                'image': self._mollie_fetch_image_by_url(method_info.get('image', {}).get('size2x')),
            })

        # Link missing methods
        all_methods = self.with_context(active_test=False).search([('is_primary', '=', True)])
        methods_to_link = []
        for method in all_methods:
            if method not in mollie_provider.payment_method_ids and method.code in mollie_methods_data.keys():
                methods_to_link.append(Command.link(method.id))

        if methods_to_link:
            mollie_provider.write({'payment_method_ids': methods_to_link})

        # generate issuers
        for method_code, method_data in mollie_methods_data.items():
            issuers_data = method_data.get('issuers', [])
            mollie_method = all_methods.filtered(lambda m: m.code == method_code)

            # remove the issuer for ideal as mollie removed the issuers support
            if mollie_method.code == 'ideal':
                mollie_method.brand_ids.write({'primary_payment_method_id': False})
                mollie_method.mollie_has_issuers = False
                continue

            if issuers_data and mollie_method:
                self._generate_issuers(issuers_data, mollie_method)

            mollie_method.mollie_has_issuers = len(mollie_method.brand_ids) > 1

        # Activate methods & update method data
        for method in mollie_provider.with_context(active_test=False).payment_method_ids:
            method.active = mollie_methods_data.get(method.code, {}).get('status') == 'activated'

    def _generate_issuers(self, issuers_data, payment_method):
        issuer_create_vals = []
        existing_issuers = payment_method.brand_ids.mapped('code')
        for issuer_info in issuers_data:
            if issuer_info['id'] not in existing_issuers:
                issuer_create_vals.append({
                    'name': issuer_info['name'],
                    'code': issuer_info['id'],
                    'active': True,
                    'image': self._mollie_fetch_image_by_url(issuer_info.get('image', {}).get('size2x')),
                    'primary_payment_method_id': payment_method.id
                })

        if issuer_create_vals:
            return self.create(issuer_create_vals)

    def _mollie_fetch_image_by_url(self, image_url):
        image_base64 = False
        try:
            image_base64 = base64.b64encode(requests.get(image_url).content)
        except Exception:
            _logger.warning('Can not import mollie image %s', image_url)
        return image_base64
