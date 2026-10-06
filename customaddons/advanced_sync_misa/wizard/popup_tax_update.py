from odoo import fields, models, api


class popupTaxUpdate(models.TransientModel):
    _name = 'popup.tax.update'

    update_option = fields.Selection([
        ('sale', 'Thuế bán hàng'),
        ('purchase', 'Thuế mua hàng'),
    ], string='Loại', default='sale')
    tax_id = fields.Many2one('account.tax', string='Thuế')
    valid_tax_ids = fields.Many2many('account.tax', compute='_compute_valid_tax_ids', compute_sudo=True)
    product_ids = fields.Many2many('product.template', string='Sản phẩm')

    @api.depends('update_option')
    def _compute_valid_tax_ids(self):
        for rec in self:
            tax_ids = self.env['account.tax'].sudo().search([('type_tax_use', '=', self.update_option)])
            rec.sudo().valid_tax_ids = tax_ids.ids

    def action_update(self):
        for product in self.product_ids:
            if self.update_option == 'sale':
                if self.tax_id:
                    product.sudo().taxes_id = [(6, 0, [self.tax_id.id])]
                else:
                    product.sudo().taxes_id = False
            elif self.update_option == 'purchase':
                if self.tax_id:
                    product.sudo().supplier_taxes_id = [(6, 0, [self.tax_id.id])]
                else:
                    product.sudo().supplier_taxes_id = False