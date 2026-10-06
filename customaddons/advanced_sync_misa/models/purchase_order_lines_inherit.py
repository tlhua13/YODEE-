from odoo import api, fields, models, _
from odoo.tools import float_round, float_compare


class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order.line'

    exchange_rate = fields.Float(string="Exchange Rate", related='order_id.exchange_rate', store=True)  # Tỷ giá
    convert = fields.Float(string='Convert', related='order_id.exchange_rate', store=True)  # Quy đổi
    standard_price = fields.Float(
        related='product_id.standard_price',string="Cost Price",
    )

    def _default_misa_credit_account(self):
        code = '331'
        account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return account.id if account else False

    def _default_misa_debit_account(self):
        code = '156'
        account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return account.id if account else False

    def _default_misa_account_inventory(self):
        code = '156'
        account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return account.id if account else False

    def _default_misa_account_receivable(self):
        code = '331'
        account = self.env['account.account.misa'].sudo().search([('code', '=', code)], limit=1)
        return account.id if account else False

    # TK Chi Phí/Kho
    misa_account_inventory = fields.Many2one('account.account.misa', string='Account Inventory/Expense', default=_default_misa_account_inventory)
    # TK Công nợ
    misa_account_receivable = fields.Many2one('account.account.misa', string='Accounts Receivable', default=_default_misa_account_receivable)

    # TK Có
    misa_credit_account = fields.Many2one('account.account.misa', string='Credit Account', default=_default_misa_credit_account)
    # TK Nợ
    misa_debit_account = fields.Many2one('account.account.misa', string='Debit Account', default=_default_misa_debit_account)

    price_subtotal = fields.Float(compute='_compute_amount', string='Subtotal', store=True)
    price_total = fields.Float(compute='_compute_amount', string='Total', store=True)

    is_service = fields.Boolean(string='Service Product', compute='_compute_is_service_product')

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            base_line = line._prepare_base_line_for_taxes_computation()
            price_unit_after_discount = base_line['price_unit'] * (1 - (base_line['discount'] / 100.0))
            taxes_computation = base_line['tax_ids']._get_tax_details(
                price_unit=price_unit_after_discount,
                quantity=base_line['quantity'],
                precision_rounding=0.01,
                rounding_method=line.company_id.tax_calculation_rounding_method,
                product=base_line['product_id'],
                special_mode=base_line['special_mode'],
            )
            # Use Float fields to avoid Monetary auto-rounding to VND (0 decimals)
            line.price_subtotal = round(taxes_computation['total_excluded'], 2)
            line.price_total = round(taxes_computation['total_included'], 2)
            line.price_tax = round(
                sum(td['tax_amount'] for td in taxes_computation['taxes_data']), 2
            )

    def _prepare_stock_moves(self, picking):
        """
        Khi giảm số lượng nhu cầu và chưa nhận hàng, mặc định Odoo sẽ tạo một
        move âm rồi biến thành phiếu "Trả hàng NCC" mới (xem _action_confirm
        core). Ở đây, nếu đang giảm (không phải MTO/move_dest_ids) và đã có
        move chưa done/cancel trên chính picking cũ, sửa thẳng product_uom_qty
        của move đó thay vì để Odoo sinh phiếu mới.
        """
        self.ensure_one()
        has_move_dests = bool(self.move_dest_ids or self.move_ids.move_dest_ids)
        if self.product_id.type == 'consu' and not has_move_dests:
            qty_to_push = self.product_qty - self._get_qty_procurement()
            if float_compare(qty_to_push, 0.0, precision_rounding=self.product_uom.rounding) < 0:
                move = self.move_ids.filtered(
                    lambda m: m.picking_id == picking and m.state not in ('done', 'cancel')
                )[:1]
                if move:
                    delta = self.product_uom._compute_quantity(
                        qty_to_push, move.product_uom, rounding_method='HALF-UP')
                    new_qty = move.product_uom_qty + delta
                    if float_compare(new_qty, 0.0, precision_rounding=move.product_uom.rounding) >= 0:
                        move.product_uom_qty = new_qty
                        return []
        return super()._prepare_stock_moves(picking)

    def action_recompute_qty_received(self):
        """Recompute qty_received from stock moves.
        incoming => +qty, outgoing => -qty
        """
        for line in self:
            if line.qty_received_method != 'stock_moves':
                continue
            total_done = 0.0
            total_all = 0.0
            for move in line.move_ids:
                code = move.picking_id.picking_type_id.code

                qty = move.product_uom._compute_quantity(move.quantity, line.product_uom, rounding_method='HALF-UP')

                sign = 1 if code in ('incoming', 'incoming_other') else -1 if code in ('outgoing', 'outgoing_other') else 0

                if sign:
                    total_all += sign * qty
                    if move.state == 'done' and move.product_id == line.product_id:
                        total_done += sign * qty

            rounding = line.product_uom.rounding
            qty_received_val = float_round(total_done, precision_rounding=rounding)

            self.env.cr.execute("""
                                UPDATE purchase_order_line
                                SET qty_received_manual = %s,
                                    qty_received        = %s,
                                    product_qty         = %s
                                WHERE id = %s
                                """, (qty_received_val, qty_received_val, total_all, line.id))

            print(
                f"id:{line.id} product:{line.product_id.default_code} "
                f"product_qty:{total_all} qty_received:{qty_received_val}"
            )

        self.invalidate_recordset(['qty_received_manual', 'qty_received', 'product_qty'])


    def action_view_order_lines(self):
        pass

    def _compute_is_service_product(self):
        for rec in self:
            is_service = False
            if rec.product_id and rec.product_id.type in ['service'] or rec.product_id.misa_features in ['service']:
                is_service = True
            rec.is_service = is_service

    @api.onchange('product_id')
    def onchange_misa_credit_account(self):
        """
        Tài khoản chi phí  Lấy theo TK Chi phí có trong sản phẩm dịch vụ để đồng bộ chứng từ mua hàng dịch vụ
        """
        for rec in self:
            if rec.product_id and rec.product_id.type in ['service']:
                if rec.product_id.misa_account_expense:
                    rec.misa_debit_account = rec.product_id.misa_account_expense.id
