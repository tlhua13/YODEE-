from odoo import fields, models, api



class StockAuditMisaDetail(models.Model):
    _name = 'stock.audit.misa.detail'

    stock_audit_misa_id = fields.Many2one('stock.audit.misa', string='Stock Audit Misa')
    lot_id = fields.Many2one('stock.lot')
    location_id = fields.Many2one('stock.location', string='Vị trí')
    product_id = fields.Many2one('product.template', string='Sản phẩm')
    quantity_on_book = fields.Float(string="Số lượng hiện có")
    quantity_audit = fields.Float(string="Số lượng đã đếm")
    diff_quantity = fields.Float(string="Chênh lêch")
    value_stock_misa = fields.Float(string="Giá trị tồn kho")