from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo import http, _
from odoo.exceptions import AccessError, MissingError


class CustomerPortalExt(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super(CustomerPortalExt, self)._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        subscription_count = request.env['sale.order'].search_count([('message_partner_ids', 'child_of', [partner.commercial_partner_id.id]),
                                                                     ('mollie_subscription_id', '!=', False),
                                                                     ('state', 'in', ['sale', 'done'])])
        values.update({'subscription_count': subscription_count})
        return values

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_subscription(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        sale_order = request.env['sale.order']
        domain = [('message_partner_ids', 'child_of', [partner.commercial_partner_id.id]),
                  ('mollie_subscription_id', '!=', None),
                  ('state', 'in', ['sale', 'done'])]

        searchbar_sortings = {'date': {'label': _('Order Date'), 'order': 'date_order desc'},
                              'name': {'label': _('Reference'), 'order': 'name'},
                              'stage': {'label': _('Stage'), 'order': 'state'},}
        # default sortby order
        if not sortby:
            sortby = 'date'
        sort_order = searchbar_sortings[sortby]['order']

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        # count for pager
        order_count = sale_order.search_count(domain)
        # pager
        pager = portal_pager(url="/my/subscriptions",
                             url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
                             total=order_count,
                             page=page,
                             step=self._items_per_page)
        # content according to pager and archive selected
        orders = sale_order.search(domain, order=sort_order, limit=self._items_per_page, offset=pager['offset'])
        values.update({'date': date_begin,
                       'subscriptions': orders.sudo(),
                       'page_name': 'subscriptions',
                       'pager': pager,
                       'default_url': '/my/subscriptions',
                       'searchbar_sortings': searchbar_sortings,
                       'sortby': sortby,})
        return request.render("mollie_subscription_ept.portal_my_subscriptions", values)

    @http.route(['/my/subscriptions/<int:subscription_id>'], type='http', auth="public", website=True)
    def portal_subscriptions_page(self, subscription_id, **kw):
        try:
            subscription_obj = self._document_check_access('mollie.subscription', subscription_id)
        except (AccessError, MissingError):
            return request.redirect('/my')

        values = {'sale_order': subscription_obj.sale_order_id,
                  'subscription_obj': subscription_obj,
                  'partner_id': subscription_obj.partner_id.id}

        if subscription_obj.sale_order_id.company_id:
            values['res_company'] = subscription_obj.sale_order_id.company_id

        return request.render('mollie_subscription_ept.portal_my_subscriptions_template', values)
