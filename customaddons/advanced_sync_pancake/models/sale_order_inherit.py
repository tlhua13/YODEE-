import json
import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from .yodee_ir_logging import YodeeIrLogging
from .pancake_connector import ORDER_STATUS_MAPPING
from datetime import date

_logger = logging.getLogger(__name__)
from odoo.tools import float_round


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    #
    pancake_status = fields.Selection(
        selection=[(key, value) for key, value in ORDER_STATUS_MAPPING.items()],
        string="Pancake Status",
    )
    pancake_order_id = fields.Char(string='Mã đơn hàng Pancake', copy=False)
    pancake_order_json = fields.Json(string='Dữ liệu đơn hàng Pancake', copy=False)
    pancake_order_json_text = fields.Text(string="Pancake Order (Text)", compute="_compute_json_text")

    pancake_source_id = fields.Many2one('pancake.order.source', string='Pancake source', copy=False, tracking=True)  # Kênh bán hàng

    total_discount_pancake = fields.Float(string='Giảm giá đơn hàng', copy=False)
    shipping_fee = fields.Float(string='Phí vận chuyển', copy=False)
    transfer_money = fields.Float(string="Transfer Money")
    order_receiver = fields.Char(string='Order Receiver')

    # phí sàn
    total_fee_marketplace = fields.Float(string='Tổng phí sàn', copy=False)

    affiliate_commission = fields.Float(string='Phí hoa hồng (Sàn TMĐT)', copy=False)
    diff_shipping_fee = fields.Float(string='Chênh lệch phí vận chuyển (Sàn TMĐT)', copy=False)
    marketplace_voucher = fields.Float(string='Sàn trợ giá', copy=False)
    payment_fee = fields.Float(string='Phí cố định, giao dịch (Sàn TMĐT)', copy=False)
    platform_commission = fields.Float(string='Phí hoa hồng nền tảng (Sàn TMĐT)', copy=False)
    seller_transaction_fee = fields.Float(string='Phí thanh toán (Sàn TMĐT)', copy=False)
    service_fee = fields.Float(string='Phí dịch vụ (Sàn TMĐT)', copy=False)
    sfp_service_fee = fields.Float(string='Phí dịch vụ SFP (Sàn TMĐT)', copy=False)

    # địa chỉ giao hàng
    shipping_full_name = fields.Char(string='Tên người nhận', copy=False)
    shipping_phone = fields.Char(string='Số điện thoại người nhận', copy=False)
    shipping_full_address = fields.Char(string='Địa chỉ giao hàng', copy=False)
    shipping_province_id = fields.Many2one('pancake.provinces', string='Tỉnh/Thành phố giao hàng', copy=False)
    shipping_district_id = fields.Many2one('pancake.districts', string='Quận/Huyện giao hàng', copy=False)
    shipping_communes_id = fields.Many2one('pancake.communes', string='Phường/Xã giao hàng', copy=False)

    internal_note = fields.Char(string='Internal note')  # Ghi chú nội bộ
    # Tổng Khuyến mãi riêng từng sản phẩm
    # pancake_total_line_discount = fields.Float('KM', compute='_compute_pancake_discount')
    pancake_after_discount = fields.Float(string="Còn phải thu", compute="_compute_pancake_discount")

    date_pancake = fields.Datetime(string='Ngày tạo Pancake', copy=False)
    date_updated_pancake = fields.Datetime(string='Cập nhật lần cuối Pancake', copy=False)

    is_paid = fields.Boolean(string='Payment completed', copy=False, tracking=True)
    account_payable = fields.Boolean(string='Accounts payable', copy=False, tracking=True)

    pancake_missing_info = fields.Boolean(string='Lack of Information Product', default=False, readonly=True)

    is_account_perm = fields.Boolean(string='Is Account Permission', compute='_compute_is_account_perm')

    sale_area_id = fields.Many2one('sale.area', string='Sale Area', related="partner_id.sale_area_id", store=True)

    combo_product_ids = fields.Many2many(
        'product.template',
        'sale_order_combo_product_rel',
        'sale_order_id',
        'product_template_id',
        string='Combo Products',
        copy=False,
    )

    partner_shipping_ids = fields.Many2many('res.partner', string='Partners', compute='_compute_is_partner_parent')
    is_partner_parent = fields.Boolean(compute='_compute_is_partner_parent')
    address_partner_detail = fields.Text(string="Address Detail")
    # validity_date = fields.Date(tracking=True)
    mark_done_cron = fields.Boolean(string='Mark Done Cron', default=False, tracking=True)
    total_diff = fields.Float(string="Total different")
    tracking_id = fields.Char(string="Tracking ID")
    @api.depends('partner_id')
    def _compute_is_partner_parent(self):
        for order in self:
            order.is_partner_parent = False
            order.partner_shipping_ids = None
            if order.partner_id.child_ids:
                order.is_partner_parent = True
                order.partner_shipping_ids = order.partner_id.child_ids + order.partner_id

    def _compute_is_account_perm(self):
        for rec in self:
            rec.is_account_perm = False
            if self.env.user.has_group('account.group_account_invoice') or self.env.user.has_group('base.group_system'):
                rec.is_account_perm = True

    def _compute_pancake_discount(self):
        for rec in self:
            # Bỏ rec.marketplace_voucher vì đã tính vào giá sản phẩm
            rec.pancake_after_discount = rec.tax_totals['total_amount'] + rec.diff_shipping_fee - rec.transfer_money - rec.total_fee_marketplace

    @api.depends("pancake_order_json")
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.pancake_order_json_text = ""
                if rec.pancake_order_json:
                    rec.pancake_order_json_text = json.dumps(rec.pancake_order_json, indent=4, ensure_ascii=False)
            except Exception:
                rec.pancake_order_json_text = ""

    def mass_action_check_paid(self):
        for rec in self:
            if not self.env.user.has_group('account.group_account_invoice'):
                raise UserError(_("Only users with Accounting permissions are allowed to perform this action."))
            if not rec.is_paid:
                rec.sudo().is_paid = True

    def mass_action_check_account_payable(self):
        for rec in self:
            if not self.env.user.has_group('account.group_account_invoice'):
                raise UserError(_("Only users with Accounting permissions are allowed to perform this action."))
            if not rec.account_payable:
                rec.sudo().account_payable = True

    @api.model
    def create(self, vals):
        if vals.get('pancake_source_id'):
            pancake = self.env['pancake.order.source'].browse(vals['pancake_source_id'])
            if pancake.is_b2b_business:
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'sale.order.b2b'
                ) or _('New')

        return super().create(vals)

    def write(self, vals):
        res = super().write(vals)
        seq = self.env['ir.sequence'].search(
            [
                ('code', '=', 'sale.order.b2b')
            ], limit=1
        )
        prefix = seq.prefix or ''

        for rec in self:
            if rec.pancake_source_id and rec.pancake_source_id.is_b2b_business and not rec.name.startswith(prefix):
                rec.write({'name': self.env['ir.sequence'].next_by_code('sale.order.b2b')})

        return res

    def split_price_including_tax(self):
        for rec in self:
            for line in rec.order_line:
                if not line.tax_id:
                    if line.price_including_tax == 0:
                        line.sudo().price_including_tax = line.price_total
                if line.price_including_tax > 0:
                    taxes = line.tax_id
                    if not taxes:
                        taxes = self.env['pancake.connector'].sudo().get_tax_product(line.product_id.id)
                    if taxes and line.product_uom_qty > 0:
                        quantity = line.product_uom_qty
                        price_unit = self.env['pancake.connector'].calculate_price_without_tax(line.price_including_tax, taxes) / quantity
                        if line.discount and line.discount != 100:
                            price_unit = price_unit / (1 - line.discount/100)
                        line.write({'tax_id': [(6, 0, taxes.ids)],
                                    'price_unit': price_unit
                                    })

    # @api.depends_context('lang')
    # @api.depends('order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    # def _compute_tax_totals(self):
    #     super()._compute_tax_totals()
    #     for order in self:
    #         if order.currency_id and order.currency_id.name == 'VND':
    #             total = order.tax_totals['total_amount']
    #             base = order.tax_totals['base_amount']
    #             tax = total - base
    #
    #             # làm tròn xuống hàng nghìn
    #             if int(total) % 100 != 0:
    #                 # làm tròn base & tax về hàng đơn vị = 0
    #                 total = float_round(total, precision_rounding=1000, rounding_method='HALF-UP')
    #                 base_rounded = float_round(base, precision_rounding=1000, rounding_method='HALF-UP')
    #                 tax_rounded = float_round(tax, precision_rounding=1000, rounding_method='HALF-UP')
    #
    #                 # bù chênh lệch để khớp total
    #                 diff = total - (base_rounded + tax_rounded)
    #                 if diff:
    #                     tax_rounded += diff
    #
    #                 # gán lại
    #                 order.tax_totals['total_amount'] = order.tax_totals['total_amount_currency'] = total
    #                 order.tax_totals['base_amount'] = order.tax_totals['base_amount_currency']  = base_rounded
    #                 order.tax_totals['tax_amount'] = order.tax_totals['tax_amount_currency'] = tax_rounded
    #
    #                 # Tính lại tổng
    #                 order.amount_total = order.tax_totals['total_amount_currency']
    #
    #
    #                 # subtotals
    #                 for subtotal in order.tax_totals.get('subtotals', []):
    #                     subtotal['base_amount'] = base_rounded
    #                     subtotal['base_amount_currency'] = base_rounded
    #
    #                     subtotal['tax_amount'] = tax_rounded
    #                     subtotal['tax_amount_currency'] = tax_rounded
    #
    #                     for tax_group in subtotal.get('tax_groups', []):
    #                         tax_group['base_amount'] = base_rounded
    #                         tax_group['base_amount_currency'] = base_rounded
    #
    #                         tax_group['tax_amount'] = tax_rounded
    #                         tax_group['tax_amount_currency'] = tax_rounded


    def mass_action_get_pancake_order_id(self):
        connector = self.env['pancake.connector']
        for rec in self:
            if rec.name:
                connector.get_order_by_id(rec.name)

    def action_apply_discount_to_price(self):
        for rec in self:
            rec.order_line.action_apply_discount_to_price()

    def action_revert_discount_to_price(self):
        for rec in self:
            rec.order_line.action_revert_discount_to_price()

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        for rec in self:
            rec.sudo().write({
                'validity_date': date.today()
            })
        return res