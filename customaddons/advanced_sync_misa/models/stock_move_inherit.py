from odoo import models, fields, api
from odoo.tools import float_round


class StockMoveInherit(models.Model):
    _inherit = 'stock.move'

    note = fields.Text(string="Ghi chú", help="Ghi chú")
    description_picking = fields.Char(string='Mô tả', related='product_id.default_code')
    product_status = fields.Boolean(related='product_id.active', string="Product Status", store=True)


    def _default_misa_debit_account(self):
        code = '331'
        debit_account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return debit_account.id if debit_account else False


    def _default_misa_account_receivable(self):
        code = '331'
        credit_account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return credit_account.id if credit_account else False

    # stock_misa = fields.Many2one('stock.location.misa', compute='_compute_stock_misa', store=True)
    stock_misa = fields.Many2one('stock.location.misa')
    stock_misa_from = fields.Many2one('stock.location.misa', compute='_compute_stock_misa_internal', store=True)
    stock_misa_to = fields.Many2one('stock.location.misa', compute='_compute_stock_misa_internal', store=True)


    # TK Nợ
    misa_debit_account = fields.Many2one('account.account.misa', string='Debit Account', compute='_compute_stock_misa_internal', store=True)
    # TK Có
    misa_credit_account = fields.Many2one('account.account.misa', string='Credit Account', compute='_compute_stock_misa_internal', store=True)
    # Tk giá vốn
    misa_cost_account = fields.Many2one('account.account.misa', string='Cost Account', compute='_compute_stock_misa_internal', store=True)
    # TK Kho
    misa_account_inventory = fields.Many2one('account.account.misa', string='Account Inventory', compute='_compute_stock_misa_internal', store=True)
    # TK Công nợ
    misa_account_receivable = fields.Many2one('account.account.misa',string='Accounts Receivable', default=_default_misa_account_receivable)

    @api.depends('product_id', 'picking_id', 'picking_id.location_dest_id',
                 'picking_id.location_id', 'picking_id.picking_type_code')
    def _compute_stock_misa_internal(self):
        for rec in self:
            picking = rec.picking_id
            stock_misa_from = False
            stock_misa_to = False
            misa_account_inventory = False
            misa_credit_account = False
            misa_debit_account = False
            misa_cost_account = False
            if picking:
                pick_type = picking.picking_type_code

                loc_from = picking.location_id.location_misa_id if picking.location_id else False
                loc_to = picking.location_dest_id.location_misa_id if picking.location_dest_id else False

                if pick_type == 'internal':
                    if loc_from:
                        stock_misa_from = loc_from.id
                    if loc_to:
                        stock_misa_to = loc_to.id

                elif pick_type == 'incoming':
                    if loc_to:
                        stock_misa_to = loc_to.id

                elif pick_type == 'outgoing':
                    if loc_from:
                        stock_misa_from = loc_from.id

                if picking.picking_type_id:
                    pt = picking.picking_type_id
                    if pt.misa_credit_account:
                        misa_credit_account = pt.misa_credit_account.id
                    if pt.misa_debit_account:
                        misa_debit_account = pt.misa_debit_account.id
                    if pt.misa_cost_account:
                        misa_cost_account = pt.misa_cost_account.id
                    if pt.misa_stock_account:
                        misa_account_inventory = pt.misa_stock_account.id

            rec.stock_misa_from = stock_misa_from
            rec.stock_misa_to = stock_misa_to
            rec.misa_account_inventory = misa_account_inventory
            rec.misa_credit_account = misa_credit_account
            rec.misa_debit_account = misa_debit_account
            rec.misa_cost_account = misa_cost_account
            rec.misa_account_inventory = misa_account_inventory


