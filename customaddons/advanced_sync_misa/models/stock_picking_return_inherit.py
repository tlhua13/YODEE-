from odoo import models
from odoo.tools import float_round

class StockReturnPickingInherit(models.TransientModel):
    _inherit = 'stock.return.picking'

    def action_create_returns_all(self):
        self.ensure_one()

        for return_move in self.product_return_moves:
            # Kiểm tra product có bị archive không
            if not return_move.product_id.active:
                return_move.quantity = 0
                continue

            stock_move = return_move.move_id
            if not stock_move or stock_move.state == 'cancel' or stock_move.scrapped:
                continue
            # Lấy số lượng
            quantity = stock_move.quantity

            # Nếu có đơn return khác thì trừ số lượng của cái đơn return đấy
            for move in stock_move.move_dest_ids:
                if not move.origin_returned_move_id or move.origin_returned_move_id != stock_move:
                    continue
                quantity -= move.quantity
            # Làm tròn
            quantity = float_round(
                quantity,
                precision_rounding=stock_move.product_id.uom_id.rounding
            )

            return_move.quantity = quantity

        return self.action_create_returns()
