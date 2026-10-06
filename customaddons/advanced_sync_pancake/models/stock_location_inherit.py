from odoo import fields, models, api


class StockLocation(models.Model):
    _inherit = 'stock.location'

    pancake_warehouse_id = fields.Many2one('pancake.warehouse', string='Kho Pancake')
    pancake_id = fields.Char(related='pancake_warehouse_id.pancake_warehouse_id', store=True)

