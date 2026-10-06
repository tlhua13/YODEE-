from markupsafe import Markup
from odoo import fields, models, api, _


class SaleOrderLineInherit(models.Model):
    _inherit = "sale.order.line"

    price_tax = fields.Float(
        string="Total Tax",
        compute='_compute_amount',
        store=True, precompute=True, readonly=False,
    )
    price_total = fields.Monetary(
        string="Total",
        compute='_compute_price_total_custom',
        store=True, precompute=True,
    )

    confirm_date = fields.Date(string='Confirmation Date', related="order_id.validity_date", store=True)
    exchange_rate = fields.Float(string="Exchange Rate", related='order_id.exchange_rate', store=True)  # Tỷ giá
    convert = fields.Float(string='Convert', related='order_id.exchange_rate', store=True)  # Quy đổi
    branch_ids= fields.Many2many(
        'pancake.branch',
        'sale_order_line_pancake_branch_rel',
        'order_line_id',
        'branch_id',
        related='product_id.pancake_brand_ids',
        string='Brand IDs',
        store= True
    )
    pancake_source_id= fields.Many2one(
        'pancake.order.source',
        related='order_id.pancake_source_id',
        string='Pancake source',
        store=True

    )
    delivery_status = fields.Selection([
        ('fully_delivered', 'Fully Delivered'),
        ('partially_delivered', 'Partially Delivered'),
        ('not_delivered', 'Not Delivered'),
    ], compute='_compute_delivery_status', store=True) # Tình trạng đơn hàng,
                                                       # 0: Chưa thực hiện; 1: Đang thực hiện; 2: Hoàn thành; 3: Đã hủy bỏ (Mặc định khi lập chứng từ
                                                       # là chưa thực hiện do đơn hàng vừa lập chưa có phiếu xuất kho, phiếu bán hàng)

    @api.depends('qty_delivered', 'product_uom_qty')
    def _compute_delivery_status(self):
        for record in self:
            if record.qty_delivered == record.product_uom_qty:
                record.delivery_status = 'fully_delivered'
            elif record.qty_delivered > 0:
                record.delivery_status = 'partially_delivered'
            else:
                record.delivery_status = 'not_delivered'

    date_order = fields.Datetime(compute='_compute_order_line_information', string= "Date order", store = True)
    customer_code = fields.Char(compute='_compute_order_line_information', string= "Customer code", store = True)
    customer_name = fields.Char(compute='_compute_order_line_information', string= "Customer name", store = True)
    product_code = fields.Char(compute='_compute_order_line_information', string= "Product code", store = True)
    # product_uom_name = fields.Char(
    #     compute='_compute_order_line_information', string= "Product uom name", store = True
    # )
    account_debit = fields.Char(compute='_compute_order_line_information', string= "Account debit", store = True)
    account_credit = fields.Char(compute='_compute_order_line_information', string= "Account credit", store = True)
    standard_price = fields.Float(string="standard price")
    warehouse_code = fields.Char(compute='_compute_order_line_information', string= "Warehouse code", store = True)
    warehouse_name = fields.Char(compute='_compute_order_line_information', string= "Warehouse name", store = True)

    return_qty = fields.Float(compute="_compute_return_qty_and_value", string="Return quantity")
    return_value = fields.Float(compute="_compute_return_qty_and_value", string="Return value")

    misa_debit_account = fields.Many2one('account.account.misa', string='Tài khoản công nợ (debit)', compute='_compute_order_line_information', store = True)
    misa_credit_account = fields.Many2one('account.account.misa', string='Tài khoản doanh thu (credit)', compute='_compute_order_line_information', store = True)
    total_fee_marketplace = fields.Float(related='order_id.total_fee_marketplace', string="Tổng phí sàn", copy=False)

    @api.depends('price_total', 'pancake_total_discount', 'product_uom_qty', 'price_unit')
    def _compute_after_discount(self):
        for rec in self:
            rec.pancake_after_discount = rec.price_total

    @api.depends('order_id','order_id.date_order','order_id.partner_id','order_id.pancake_order_id',
        'order_id.pancake_source_id','order_id.warehouse_id','product_id')
    def _compute_order_line_information(self):
        for rec in self:
            order = rec.order_id
            partner = order.partner_id if order else False
            source = order.pancake_source_id if order else False
            warehouse = order.warehouse_id if order else False

            # Date order
            rec.date_order = order.date_order if order else False

            # Customer
            rec.customer_code = (
                order.pancake_order_id
                if order and order.pancake_order_id
                else partner.customer_code if partner else False
            )
            rec.customer_name = partner.name if partner else False

            # Product
            rec.product_code = rec.product_id.code if rec.product_id else False

            # MISA accounts
            rec.misa_credit_account = source.misa_credit_account if source else False
            rec.misa_debit_account = source.misa_debit_account if source else False

            # Warehouse
            rec.warehouse_code = warehouse.code if warehouse else ""
            rec.warehouse_name = warehouse.name if warehouse else ""

    def _compute_return_qty_and_value(self):
        for rec in self:
               # Default
            rec.return_qty = 0
            rec.return_value = 0

            # Lấy move DONE của sale line
            moves = self.env['stock.move'].search([
                ('sale_line_id', '=', rec.id),
                ('state', '=', 'done'),
            ])
            moves_not_return = self.env['stock.move'].search([
                ('sale_line_id', '=', rec.id),
                ('origin_returned_move_id', '=', False),
            ])

            if not moves:
                continue

            cost = rec.price_unit or 0
            qty_return_total = 0

            # Tìm return move của từng move gốc
            for move in moves_not_return:
                return_moves = self.env['stock.move'].search([
                    ('origin_returned_move_id', '=', move.id),
                    ('product_id', '=', rec.product_id.id),
                    ('state', '=', 'done'),
                    ('to_refund', '=', True),
                ])

                for r_move in return_moves:
                    # Ưu tiên qty_done trên move line
                    if r_move.move_line_ids:
                        qty_return_total += sum(
                            r_move.move_line_ids.mapped('qty_done')
                        )
                    else:
                        # fallback
                        qty_return_total += r_move.quantity_done

            rec.return_qty = qty_return_total
            rec.return_value = qty_return_total * cost

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    def _compute_amount(self):
        for line in self:
            base_line = line._prepare_base_line_for_taxes_computation()
            self.env['account.tax']._add_tax_details_in_base_line(base_line, line.company_id)
            line.price_subtotal = base_line['tax_details']['raw_total_excluded_currency']
            line.price_tax = base_line['tax_details']['raw_total_included_currency'] - line.price_subtotal

    @api.depends('price_subtotal', 'price_tax')
    def _compute_price_total_custom(self):
        for line in self:
            line.price_total = line.price_subtotal + line.price_tax

    def write(self, vals):
        if 'price_tax' in vals:
            for line in self:
                if line.order_id and line.order_id.is_used_custom_tax:
                    old_val = line.price_tax
                    new_val = vals.get('price_tax', old_val)
                    if old_val != new_val:
                        product_name = line.product_id.display_name or line.name or ''
                        currency = line.order_id.currency_id
                        old_formatted = f"{currency.symbol} {old_val:,.2f}" if currency else f"{old_val:,.2f}"
                        new_formatted = f"{currency.symbol} {new_val:,.2f}" if currency else f"{new_val:,.2f}"
                        lang = self.env.lang or 'en_US'
                        if lang == 'vi_VN':
                            body = Markup(
                                "<b>Tiền thuế</b> cập nhật trên dòng "
                                "<span>%s</span>:<br/>"
                                "%s → %s"
                            ) % (product_name, old_formatted, new_formatted)
                        else:
                            body = Markup(
                                "<b>Tax Amount</b> updated on line "
                                "<span>%s</span>:<br/>"
                                "%s → %s"
                            ) % (product_name, old_formatted, new_formatted)
                        line.order_id.message_post(body=body)
        return super().write(vals)