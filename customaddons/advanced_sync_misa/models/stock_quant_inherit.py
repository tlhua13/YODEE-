from odoo import fields, models, api, _
from odoo.exceptions import UserError


class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    quantity_misa = fields.Float(string="Quantity (Misa)")
    value_stock_misa = fields.Float(string="Giá trị tồn kho")
    # standard_price = fields.Float(string="Giá vốn", related='product_id.standard_price', store=True)

    def _get_inventory_fields_write(self):
        return ['value_stock_misa','id'] + super()._get_inventory_fields_write()

    def create_audit_misa(self):
        print(self)
        view = self.env.ref('advanced_sync_misa.stock_audit_misa_form_view')
        if not self:
            raise UserError(_(f'Vui lòng chọn dòng để kiểm kê!'))

        data_sync = []
        # Tích chọn dòng nào sẽ kiểm kê dòng đó
        for rec in self:
            data = {
                'location_id': rec.location_id.id,
                'product_id': rec.product_id.id,
                'quantity_on_book': rec.quantity,
                'quantity_audit': rec.inventory_quantity,
                'diff_quantity': rec.inventory_diff_quantity,
                'value_stock_misa': rec.value_stock_misa,
            }
            data_sync.append((0, 0, data))
            rec.sudo().value_stock_misa = 0.0  # Reset giá trị tồn kho sau khi tạo phiếu kiểm kê
        new_audit = self.env['stock.audit.misa'].create({
            'stock_quant_sync': data_sync if data_sync else False,
        })
        return {
            'name': _('Kiểm kê (Misa)'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.audit.misa',
            'view_mode': 'form',
            'view_id': view.id,
            'res_id': new_audit.id,
            'target': 'new',
        }

    def action_apply_inventory(self):
        user = self.env.user

        if not (
                user.has_group('advanced_sync_misa.group_allow_update_physical_inventory')
                or user.has_group('base.group_system')
        ):
            raise UserError(_(
                "User doesn't have permission to update the inventory.\n"
                "Please contact the administrator to grant permission."
            ))

        return super().action_apply_inventory()

