from odoo import fields, models, api


class StockPickingTypeInherit(models.Model):
    _inherit = 'stock.picking.type'

    is_return = fields.Boolean(default=False)
    location_address_id = fields.Many2one('res.partner', string='Location Address')
    misa_debit_account = fields.Many2one('account.account.misa', string='TK nợ')
    misa_credit_account = fields.Many2one('account.account.misa', string='TK có')
    misa_stock_account = fields.Many2one('account.account.misa', string='Stock account')
    misa_cost_account = fields.Many2one('account.account.misa', string='Cost account')
    is_misa_return = fields.Boolean(default=False)
    code = fields.Selection(
        selection_add=[
            ('incoming_other', 'Incoming Other'),
            ('outgoing_other', 'Outgoing Other'),
            ('product', 'Product')
        ],
        ondelete={'incoming_other': 'set default', 'outgoing_other': 'set default', 'product': 'set default'},
    )
    default_customer = fields.Many2one('res.partner', string='Default Customer', required=True)
    @api.depends('code')
    def _compute_show_picking_type(self):
        super()._compute_show_picking_type()
        for pt in self:
            if pt.code in ['incoming_other', 'outgoing_other', 'product']:
                pt.show_picking_type = True