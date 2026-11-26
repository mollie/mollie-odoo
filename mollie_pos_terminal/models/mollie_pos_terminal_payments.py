from odoo import api, fields, models


class MolliePosTerminalPayments(models.Model):
    _name = 'mollie.pos.terminal.payments'
    _description = 'Mollie POS Terminal Payment'

    name = fields.Char("Transaction ID", index=True)
    mollie_uid = fields.Char("Mollie UID", index=True)
    order_uuid = fields.Char("POS Order UUID", index=True)
    payment_method_id = fields.Many2one('pos.payment.method')
    terminal_id = fields.Many2one('mollie.pos.terminal')
    session_id = fields.Many2one('pos.session')
    mollie_latest_response = fields.Json('Response', default={})
    status = fields.Selection([
        ('open', 'Open'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('canceled', 'Canceled'),
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('processing', 'Processing'),
    ], default='open')
    parent_payment_id = fields.Many2one("mollie.pos.terminal.payments", string='Origin payment')
    refund_payment_ids = fields.One2many("mollie.pos.terminal.payments", 'parent_payment_id', string='Refunds')

    @api.model
    def _mollie_log(self, data, payment_method, mollie_uid, session_id, parent_payment=None, order_uuid=None):
        """Log a payment or refund that was just created at Mollie."""
        return self.create({
            'name': data['id'],
            'mollie_uid': mollie_uid,
            'order_uuid': order_uuid,
            'payment_method_id': payment_method.id,
            'terminal_id': payment_method.mollie_pos_terminal_id.id,
            'session_id': self.env['pos.session'].browse(session_id).exists().id,
            'parent_payment_id': parent_payment and parent_payment.id,
            **self._mollie_status_vals(data),
        })

    @api.model
    def _mollie_update(self, payment):
        """Store Mollie's latest data on the rows of a payment and its embedded refunds, when their status changed."""
        for data in [payment, *payment.get('_embedded', {}).get('refunds', [])]:
            row = self.search([('name', '=', data.get('id'))], limit=1)
            if row and (row.mollie_latest_response or {}).get('status') != data.get('status'):
                row.write(self._mollie_status_vals(data))

    @api.model
    def _mollie_status_vals(self, data):
        # A status outside the selection (e.g. 'authorized') only updates the stored response.
        vals = {'mollie_latest_response': data}
        if data.get('status') in dict(self._fields['status'].selection):
            vals['status'] = data['status']
        return vals
