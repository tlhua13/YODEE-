from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrderInherit(models.Model):
    _inherit = 'pos.order'

    points = fields.Float(related='partner_id.points')

    pos_invoice_number = fields.Char(string='Số hóa đơn POS', compute='_compute_account_move', store=True)



    @api.depends('account_move', 'account_move.name')
    def _compute_account_move(self):
        for move in self:
            invoice = move.account_move[:1]
            move.pos_invoice_number = invoice.name if invoice else ''

    @api.model
    def create(self, vals):
        if vals.get('pos_reference'):
                vals['pos_reference'] = self.env['ir.sequence'].next_by_code(
                    'invoice.pos.yodee'
                ) or _('New')
        return super().create(vals)
