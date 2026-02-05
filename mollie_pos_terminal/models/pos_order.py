from odoo import  models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def add_payment(self, data):
        transaction_id = self.env.context.get('mollie_refund_transaction_id', False)
        if transaction_id:
            data.update({
                'transaction_id': transaction_id
            })
        return super().add_payment(data)