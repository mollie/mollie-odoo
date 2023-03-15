import logging
from odoo import fields, http
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class WebsiteSale(WebsiteSale):

    @http.route(['/clear_warn'], type='json', auth="public", website=True)
    def clear_warning(self, **post):
        request.session['show_wishlist_warn'] = request.session['show_in_cart_warn'] = not (post.get('hide_warn'))
        return True

    def _set_session(self, so_obj):
        request.session['show_wishlist_warn'] = True if so_obj.get('show_wishlist_warning') else False
        request.session['show_in_cart_warn'] = True if so_obj.get('show_in_cart_warning') else False

    @http.route(['/shop/cart/update'], type='http', auth="public", methods=['POST'], website=True)
    def cart_update(self, product_id, add_qty=1, set_qty=0, **kw):
        """This route is called when adding a product to cart (no options)."""
        sale_order = request.website.sale_get_order(force_create=True)
        if sale_order.state != 'draft':
            request.session['sale_order_id'] = None
            sale_order = request.website.sale_get_order(force_create=True)

        product_custom_attribute_values = None
        if kw.get('product_custom_attribute_values'):
            product_custom_attribute_values = json_scriptsafe.loads(kw.get('product_custom_attribute_values'))

        no_variant_attribute_values = None
        if kw.get('no_variant_attribute_values'):
            no_variant_attribute_values = json_scriptsafe.loads(kw.get('no_variant_attribute_values'))

        values = sale_order._cart_update(product_id=int(product_id),
                                         add_qty=add_qty,
                                         set_qty=set_qty,
                                         product_custom_attribute_values=product_custom_attribute_values,
                                         no_variant_attribute_values=no_variant_attribute_values)

        self._set_session(values)

        if kw.get('express'):
            return request.redirect("/shop/checkout?express=1")

        return request.redirect("/shop/cart")

    @http.route(['/shop/cart/update_json'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def cart_update_json(self, product_id, line_id=None, add_qty=None, set_qty=None, display=True, **kw):
        """
        This route is called :
            - When changing quantity from the cart.
            - When adding a product from the wishlist.
            - When adding a product to cart on the same page (without redirection).
        """
        values = super(WebsiteSale, self).cart_update_json(product_id=product_id,
                                                           line_id=line_id,
                                                           add_qty=add_qty,
                                                           set_qty=set_qty,
                                                           display=display, **kw)

        self._set_session(values)

        return values

class MolliePayment(WebsiteSale):

    def _get_shop_payment_values(self, order, **kwargs):
        """
        show only mollie's credit card payment method when checkout subscription type product
        """
        values = super(MolliePayment, self)._get_shop_payment_values(order, **kwargs)
        if order:
            check_is_subscription = order._check_subs_in_cart()
            if check_is_subscription:
                values['acquirers'] = values['acquirers'].filtered(lambda x: x.provider == 'mollie')
        return values
