from odoo import models, fields, api

class StockMoveLineInherit(models.Model):
    _inherit = 'stock.move.line'

    origin = fields.Char(
        related='picking_id.origin',
        store=True,
        string='Origin',
    )






