from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    mollie_voucher_category = fields.Selection([
        ('meal', 'Meal'),
        ('eco', 'Eco'),
        ('gift', 'Gift'),
        ('sport_culture', 'Sports & Culture'),
    ], compute='_compute_mollie_voucher_category')

    def _compute_mollie_voucher_category(self):
        vouchers = self.env['pos.mollie.voucher'].search([])
        for product in self:
            # A rule on the product wins over one on its category; a category rule covers its sub-categories.
            categ_ids = {int(categ_id) for categ_id in (product.categ_id.parent_path or '').split('/') if categ_id}
            voucher = (
                vouchers.filtered(lambda v: product._origin in v.product_ids)[:1]
                or vouchers.filtered(lambda v: categ_ids & set(v.category_ids.ids))[:1]
            )
            product.mollie_voucher_category = voucher.mollie_voucher_category

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ['mollie_voucher_category']
