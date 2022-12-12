from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mollie_subscription_id = fields.One2many("mollie.subscription", "sale_order_id", "Subscription")

    def _check_subs_in_cart(self):
        result = self.order_line.product_id.filtered(lambda product: product.is_mollie_subscription)
        res = False
        if result:
            res = True
        return res

    def _public_user(self):
        public_partner_id = self.env.ref("base.public_user") and self.env.ref("base.public_user").partner_id or False
        current_partner_id = self.partner_id or False
        if public_partner_id.id == current_partner_id.id:
            return True
        else:
            return False

    def add_to_wishlist(self, line_obj):
        self.env['product.wishlist'].create({'partner_id': self.partner_id.id or False,
                                             'product_id': line_obj.product_id.id or False,
                                             'currency_id': line_obj.currency_id.id or False,
                                             'pricelist_id': self.pricelist_id.id or False,
                                             'price': line_obj.price_unit or False,
                                             'website_id': self.website_id.id or False})

    def _cart_update(self, product_id=None, line_id=None, add_qty=0, set_qty=0, **kwargs):
        product_obj = self.env['product.product'].browse(product_id)
        values = {}
        if product_obj:
            if self._check_subs_in_cart() and not product_obj.is_mollie_subscription:
                return {'show_in_cart_warning': True}

            values = super(SaleOrder, self)._cart_update(product_id, line_id, add_qty, set_qty, **kwargs)

            # If any non-subscription products available in the cart, move those products to the wishlist
            if product_obj.is_mollie_subscription:
                order_line = self.order_line.filtered(lambda x: not x.product_id.is_mollie_subscription)
                for line in order_line:
                    if not line.product_id._is_in_wishlist() and not self._public_user():
                        self.add_to_wishlist(line)
                        values.update({'show_wishlist_warning': True})
                    line.unlink()
        return values
