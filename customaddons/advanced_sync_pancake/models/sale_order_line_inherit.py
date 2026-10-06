
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)
from odoo.tools import float_round


class SaleOrderLineInherit(models.Model):
    _inherit = 'sale.order.line'

    pancake_id = fields.Char()
    pancake_order_id = fields.Char(string='Mã đơn hàng Pancake', related='order_id.pancake_order_id', store=True)
    pancake_source_id = fields.Many2one('pancake.order.source', string='Pancake source', related='order_id.pancake_source_id', store=True) #Kênh bán hàng

    pancake_total_discount = fields.Float(string="KM(Pancake)")
    pancake_after_discount = fields.Float(string="Tổng sau KM", compute="_compute_after_discount")

    price_including_tax = fields.Float(string="Price Including Tax")
    sale_area_id = fields.Many2one('sale.area', string='Sale Area', related="order_partner_id.sale_area_id", store=True)

    price_unit_before_discount = fields.Float(string="Đơn giá trước chiết khấu", copy=False)
    discount_before_apply = fields.Float(string="% Chiết khấu trước khi áp dụng", copy=False)

    def action_apply_discount_to_price(self):
        for line in self:
            if line.discount:
                line.price_unit_before_discount = line.price_unit
                line.discount_before_apply = line.discount
                line.price_unit = line.price_unit - line.price_unit * line.discount / 100
                line.discount = 0

    def action_revert_discount_to_price(self):
        for line in self:
            if line.discount_before_apply or line.price_unit_before_discount:
                line.price_unit = line.price_unit_before_discount
                line.discount = line.discount_before_apply
                line.price_unit_before_discount = 0
                line.discount_before_apply = 0

    @api.depends('product_id', 'linked_line_id', 'linked_line_ids')
    def _compute_name(self):
        for line in self:
            if not line.product_id and not line.is_downpayment:
                continue

            lang = line.order_id._get_lang()
            if lang != self.env.lang:
                line = line.with_context(lang=lang)

            if line.product_id:
                if line.product_id.description_sale:
                    line.name = f"[{line.product_id.default_code}] {line.product_id.description_sale}"
                else:
                    line.name = f"[{line.product_id.default_code}] {line.product_id.name}"
                continue

            if line.is_downpayment:
                line.name = line._get_downpayment_description()


    # @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id')
    # def _compute_amount(self):
    #     # giữ nguyên logic gốc
    #     super()._compute_amount()
    #
    #     for line in self:
    #         if line.currency_id and line.currency_id.name == 'VND':
    #             if int(line.price_total) % 10 != 0:
    #                 # hàng chục và hàng trăm đều = 0
    #                 if (line.price_total % 1000) // 100 == 0 and (line.price_total % 100) // 10 == 0:
    #                     line.price_total = float_round(
    #                         line.price_total,
    #                         precision_rounding=10,
    #                         rounding_method='DOWN'
    #                     )
    #                 elif (line.price_total % 1000) // 100 == 9 and (line.price_total % 100) // 10 == 9:
    #                     line.price_total = float_round(
    #                         line.price_total,
    #                         precision_rounding=1000,
    #                         rounding_method='HALF-UP'
    #                     )




