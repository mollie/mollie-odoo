from odoo.addons.website_sale.controllers.main import WebsiteSale


class MolliePayment(WebsiteSale):

    def _get_shop_payment_values(self, order, **kwargs):
        """
        show only mollie's credit card payment method when checkout subscription type product
        """
        values = super(MolliePayment, self)._get_shop_payment_values(order, **kwargs)

        if order:
            check_is_subscription = order._check_subs_in_cart()
            if check_is_subscription:
                acquirers = values['acquirers']
                values['acquirers'] = acquirers.filtered(lambda x: x.provider == 'mollie')

        return values
