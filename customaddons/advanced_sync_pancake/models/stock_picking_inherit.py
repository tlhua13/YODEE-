from odoo import fields, models, api, _
from odoo.exceptions import UserError
import traceback
class StockPickingIherit(models.Model):
    _inherit = 'stock.picking'

    origin = fields.Char(tracking=True)
    pancake_order_id = fields.Char(string='Mã đơn hàng Pancake', related='sale_id.pancake_order_id', store=True, copy=False)
    address_partner_detail = fields.Text(compute='_compute_address_partner_detail', store=True, readonly=False)

    date_pancake = fields.Datetime(string='Ngày tạo Pancake', related='sale_id.date_pancake', store=True)
    date_updated_pancake = fields.Datetime(string='Cập nhật lần cuối Pancake', related='sale_id.date_updated_pancake', store=True)



    def action_assign(self):
        return super(StockPickingIherit, self).action_assign()

    # def button_validate(self):
    #     self._check_availability_stock(self)
    #     return super(StockPickingIherit, self).button_validate()



    # def _check_availability_stock(self, pickings):
    #     for picking in pickings:
    #         if self._is_outgoing_transfer(picking) or  self._is_internal_transfer(picking):
    #             moves = picking.move_ids_without_package
    #
    #             # Lấy tất cả qty_available theo sản phẩm 1 lần
    #             product_qty_available = {
    #                 product.id: product.with_context(location=picking.location_id.id).qty_available
    #                 for product in moves.mapped('product_id')
    #             }
    #
    #             # Danh sách sản phẩm thiếu tồn kho
    #             products_short_stock = []
    #             for move in moves:
    #                 qty_on_hand = product_qty_available.get(move.product_id.id, 0.0)
    #                 # Kiểm tra SL thực tế
    #                 if move.quantity > 0:
    #                     if move.quantity > qty_on_hand:
    #                         display_name = self.shorten_name(move.product_id.display_name)
    #                         products_short_stock.append(
    #                             "%s - %s ( Tồn kho: %.2f, Yêu cầu: %.2f)" % (
    #                                 picking.name,
    #                                 display_name,
    #                                 qty_on_hand,
    #                                 move.quantity
    #                             )
    #                         )
    #
    #             if products_short_stock:
    #                 message = "Không thể xác nhận xuất kho vì tồn kho không đủ cho các sản phẩm sau:\n"
    #                 message += "\n".join(products_short_stock)
    #                 raise UserError(_(message))

    def _is_outgoing_transfer(self, picking):
        """Kiểm tra nếu là xuất kho bán hàng"""
        return picking.location_id.usage == 'internal' and picking.location_dest_id.usage not in ['internal', 'view', 'transit']

    def _is_internal_transfer(self, picking):
        """Kiểm tra nếu là xuất kho bán hàng"""
        return picking.location_id.usage == 'internal' and picking.location_dest_id.usage == 'internal'


    # Tên sản phẩm dài quá hiển thị ngắn gọn lại
    def shorten_name(self, name, limit=60):
        if len(name) <= limit:
            return name
        # Tìm vị trí cắt ở gần limit nhất nhưng không cắt giữa chữ
        cut_pos = name.rfind(" ", 0, limit)
        if cut_pos == -1:
            return name[:limit] + "..."

        return name[:cut_pos] + "..."

    @api.model
    def create(self, vals):
        records = super().create(vals)

        for rec in records:
            # Sửa tên DO theo chứng từ gốc
            if rec.return_id and rec.return_id.origin:
                base_name = f"{rec.return_id.origin}_return"
            elif rec.origin and  rec.picking_type_code != 'internal':
                base_name = rec.origin
            else:
                continue

            # Kiểm tra check trùng thì thêm time vào
            exists = self.env['stock.picking'].search(
                [('name', '=', base_name), ('id', '!=', rec.id)],
                limit=1
            )

            if exists:
                create_dt = fields.Datetime.context_timestamp(rec, rec.create_date)
                time_str = create_dt.strftime('%d%m%y%H%M')
                rec.name = f"{base_name}_{time_str}"
            else:
                rec.name = base_name
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'origin' in vals:
            for rec in self:
                if not rec.origin or not rec.sale_id or rec.picking_type_code == 'internal':
                    continue


                # Tên DO lấy theo mã chứng từ gốc
                base_name = rec.origin
                # Trường hợp trả hàng lấy mã chứng từ của đơn hàng gốc
                if rec.return_id and rec.return_id.origin:
                    base_name = f"{rec.return_id.origin}_return"

                # Nếu name đã đúng thì bỏ qua
                if rec.name == base_name:
                    continue

                exists = self.env['stock.picking'].search(
                    [('name', '=', base_name), ('id', '!=', rec.id)],
                    limit=1
                )

                if exists:
                    create_dt = fields.Datetime.context_timestamp(rec, rec.create_date)
                    time_str = create_dt.strftime('%d%m%y%H%M')
                    rec.name = f"{base_name}_{time_str}"
                else:
                    rec.name = base_name

        return res

    @api.depends('partner_id','sale_id', 'sale_id.shipping_full_address','sale_id.address_partner_detail')
    def _compute_address_partner_detail(self):
        for rec in self:
            if rec.sale_id and rec.sale_id.address_partner_detail:
                rec.address_partner_detail = rec.sale_id.address_partner_detail
            elif rec.sale_id and rec.sale_id.shipping_full_address:
                rec.address_partner_detail = rec.sale_id.shipping_full_address
            elif rec.partner_id and rec.partner_id.street:
                rec.address_partner_detail = rec.partner_id.street
            else :
                rec.address_partner_detail = None

    def unlink(self):
        IrLogging = self.env['ir.logging'].sudo()
        user = self.env.user

        for picking in self:
            if picking.origin and picking.picking_type_code == 'outgoing':
                IrLogging.create({
                    'name': 'DO_UNLINK',
                    'type': 'server',
                    'level': 'CRITICAL',
                    'message': f"""
                        DO BỊ XOÁ
                        Picking: {picking.name}
                        SO: {picking.origin}
                        State: {picking.state}
                        User: {user.name} (ID: {user.id})
                        """,
                    'path': 'stock.picking',
                    'func': 'unlink',
                    'line': 0,
                })

        return super().unlink()