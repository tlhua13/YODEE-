from odoo import fields, models, api

VOUCHER_TYPE = [
    ('0', 'Chưa xác định'),
    ('1', 'Thu tiền gửi'),
    ('2', 'Chuyển tiền nội bộ'),
    ('3', 'Chi tiền gửi'),
    ('4', 'Phiếu chi'),
    ('5', 'Phiếu thu'),
    ('6', 'Chứng từ nghiệp vụ khác'),
    ('7', 'Nhập kho'),
    ('8', 'Xuất kho'),
    ('9', 'Chuyển kho'),
    ('10', 'Bán giảm giá'),
    ('11', 'Hóa đơn bán hàng'),
    ('12', 'Bán trả lại'),
    ('13', 'Bán hàng'),
    ('14', 'Mua giảm giá'),
    ('15', 'Hóa đơn mua hàng'),
    ('16', 'Mua trả lại'),
    ('17', 'Mua dịch vụ'),
    ('18', 'Mua hàng'),
    ('19', 'Kiểm kê kho'),
    ('20', 'Đơn đặt hàng'),
    ('21', 'Đơn mua hàng'),
]


class CallbackMisa(models.Model):
    _name = 'callback.misa'

    org_refid = fields.Char()
    success = fields.Boolean(default=False, string="Syn Misa")
    success_odoo = fields.Boolean(compute='_compute_success_odoo', store=True, string="Syn Odoo")
    error_message = fields.Char()
    session_id = fields.Char()
    voucher_type = fields.Char()
    signature = fields.Char()
    transaction_type = fields.Selection(
        selection=VOUCHER_TYPE,
        string='Transaction Type'
    )



    purchase_id = fields.Many2one('purchase.order', string='Purchase Order')
    sale_order_id = fields.Many2one('sale.order', 'Sale Order')
    picking_id = fields.Many2one('stock.picking', string='Stock Picking')
    stock_audit_misa_id = fields.Many2one('stock.audit.misa', string='Stock Audit Misa')

    @api.depends('purchase_id','sale_order_id','picking_id')
    def _compute_success_odoo(self):
        for rec in self:
            success_odoo = False
            if rec.purchase_id or rec.sale_order_id or rec.picking_id:
                success_odoo = True
            rec.success_odoo = success_odoo
    def update_link_data_callback_misa(self):
        for rec in self:
            voucher_type = int(rec.voucher_type)
            org_refid = rec.org_refid
            if org_refid:
                if 0 <= voucher_type <= 21:
                    # Đơn mua hàng
                    # Mua hàng dịch vụ
                    if voucher_type in [17, 21]:
                        data_ref = self.env['purchase.order'].sudo().search(['|', ('misa_id', '=', org_refid), ('misa_pu_invoice_id', '=', org_refid)])
                        if data_ref:
                            data_ref.finish_sync_misa = True
                            rec.purchase_id = data_ref.id
                    # Đơn đặt hàng
                    if voucher_type in [20]:
                        data_ref = self.env['sale.order'].sudo().search([('misa_id', '=', org_refid)])
                        if data_ref:
                            data_ref.finish_sync_misa = True
                            rec.sale_order_id = data_ref.id
                    # Nhập kho, Xuất kho, Chuyển kho, Mua hàng
                    if voucher_type in [7, 8, 9, 18]:
                        data_ref = self.env['stock.picking'].sudo().search([('misa_id', '=', org_refid)])
                        if data_ref:
                            data_ref.finish_sync_misa = True
                            rec.picking_id = data_ref.id
                    # Kiểm kê kho
                    if voucher_type in [19]:
                        data_ref = self.env['stock.audit.misa'].sudo().search([('misa_id', '=', org_refid)])
                        if data_ref:
                            data_ref.finish_sync_misa = True
                            rec.stock_audit_misa_id = data_ref.id
