from odoo import fields, models, api


class StockLocation(models.Model):
    _inherit = 'stock.location'
    _order = 'id DESC'

    location_misa_id = fields.Many2one('stock.location.misa', string='Location Misa')
    stock_misa_code = fields.Char(string='Location Misa Code', related='location_misa_id.code', store=True)
    is_not_submit = fields.Boolean(string="Kho ảo (Không lưu tồn kho)")
