from odoo import fields, models, api


class popupiMsaFeaturesUpdate(models.TransientModel):
    _name = 'popup.misa.features.update'

    update_option = fields.Selection([('component', 'Component'),
                                      ('product', 'Product'),
                                      ('goods', 'Goods'),
                                      ('service', 'Service'),
                                      ('end_products', 'Finished Product'),
                                      ('equipment', 'Tools and equipment'),
                                      ], string="Misa Features")
    product_ids = fields.Many2many('product.template', string='Sản phẩm')

    def action_update(self):
        self.sudo().product_ids.write({'misa_features': self.update_option})
        for product in self.product_ids:
            product._onchange_misa_features()

    def unlink(self):
        # Thêm guard để tránh autovacuum crash
        if self.env.context.get('autovacuum_running'):
            print('autovacuum_running')
            return super().unlink()
        return super().unlink()