from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrderInherit(models.Model):
    _inherit = 'pos.order.line'

    brand_ids = fields.Many2many(
        'pancake.branch',
        compute='_compute_brand_ids',
        store=True,
    )

    seller_id = fields.Many2one('res.users', store=True, related='order_id.user_id', string='Seller')
    session_id = fields.Many2one('pos.session', store=True, related='order_id.session_id', string='Session')
    config_id = fields.Many2one('pos.config', store=True, related='order_id.config_id', string='POS')
    partner_id = fields.Many2one('res.partner', store=True, related='order_id.partner_id', string='Customer')
    order_note = fields.Text(string='Note')
    direct_discount_amount = fields.Float(string='Direct Discount (VND)', digits=(16, 2), default=0.0)

    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        fields.append('direct_discount_amount')
        return fields

    @api.depends('product_id', 'product_id.pancake_brand_ids')
    def _compute_brand_ids(self):
        for line in self:
            line.brand_ids = line.product_id.pancake_brand_ids if line.product_id else False

