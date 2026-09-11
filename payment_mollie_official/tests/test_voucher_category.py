# -*- coding: utf-8 -*-

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestMollieVoucherCategory(TransactionCase):

    def test_category_follows_selected_issuer(self):
        product = self.env['product.template'].create({'name': 'Voucher product'})
        VoucherLine = self.env['mollie.voucher.line']
        VoucherLine.create({'mollie_voucher_category': 'eco', 'product_ids': [(4, product.id)]})
        VoucherLine.create({'mollie_voucher_category': 'gift', 'product_ids': [(4, product.id)]})
        categories = product._get_mollie_voucher_category()
        self.assertEqual(sorted(categories), ['eco', 'gift'])

        def category_for(issuer):
            tx = self.env['payment.transaction'].new({'mollie_payment_issuer': issuer})
            return tx._mollie_voucher_category_for_issuer(categories)

        self.assertEqual(category_for('monizze-belgium-gift'), 'gift')
        self.assertEqual(category_for('edenred-belgium-eco'), 'eco')
        # Unknown issuer or no issuer: previous behaviour, first configured category
        self.assertEqual(category_for('unknown-issuer'), categories[0])
        self.assertEqual(category_for(False), categories[0])
