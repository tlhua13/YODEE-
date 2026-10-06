from odoo import fields, models, api


class PancakeProductTemplate(models.Model):
    _name = 'pancake.product.template'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _description = 'Sản phẩm mẫu'
    _rec_name = 'display_name'

    name = fields.Char(string="Tên")
    default_code = fields.Char(string="Mã tham chiếu nội bộ")
    description = fields.Char()
    pancake_product_template_id = fields.Char(string='Pancake Product Template ID')
    product_template_ids = fields.One2many('product.template','pancake_product_template_id', string='Sản phẩm thuộc tính', readonly=True)
    product_template_json = fields.Json(string='Product Template JSON')
    pancake_barcode = fields.Char(string="Barcode from Pancake")
    pancake_supplier = fields.Char(string="Nhà cung cấp Pancake")
    display_name = fields.Char(compute='_compute_display_name')

    @api.depends('name','default_code')
    def _compute_display_name(self):
        for rec in self:
            if rec.default_code:
                rec.display_name = f"[{rec.default_code}] {rec.name}"
            else:
                rec.display_name = rec.name


