from odoo import api, fields, models, _
import requests
import json
from datetime import datetime, timedelta
import pytz
from odoo.exceptions import UserError
from bs4 import BeautifulSoup

from odoo import api, fields, models

from odoo.exceptions import UserError
from datetime import datetime


class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    misa_status = fields.Selection([('not_synced', 'Unsynchronized'),
                                    ('synced', 'Synchronized'),
                                    ('sync_failed', 'Synchronization Failed'),
                                    ], string='Misa Status', default='not_synced', copy=False)
    finish_sync_misa = fields.Boolean(string='Finish Sync Misa', default=False, copy=False)
    number_of_days_owed = fields.Integer(string='Number of days owed')
    misa_id = fields.Char(string='Misa ID', compute='_compute_misa_id', store=True)
    noti_status_misa = fields.Char(string='Noti Status', compute='compute_noti_status_misa')

    exchange_rate = fields.Float(string="Exchange Rate", default=1, tracking=True)  # Tỷ giá
    convert = fields.Float(string='Convert', default=1, tracking=True)  # Quy đổi

    check_currency_vnd = fields.Boolean(string='Check Currency VND', compute='compute_check_currency')
    is_wholesaler = fields.Boolean(string='Is Wholesale Customer', related='partner_id.is_wholesaler', store=True)
    name_wholesaler = fields.Char(string='Wholesaler Customer', related='partner_id.name_wholesaler', store=True)
    is_used_custom_tax =  fields.Boolean(string='Custom Tax Input', default=False, tracking=True)

    yodee_invoice_number = fields.Char(string='Ký hiệu HĐ', tracking=True)
    yodee_invoice_code = fields.Char(string='Số hóa đơn', tracking=True)
    yodee_invoice_date = fields.Date(string='Ngày HĐ', tracking=True)

    @api.depends_context('lang')
    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'currency_id', 'company_id', 'payment_term_id',
                 'is_used_custom_tax')
    def _compute_tax_totals(self):
        AccountTax = self.env['account.tax']
        for order in self:
            if order.is_used_custom_tax:
                order_lines = order.order_line.filtered(lambda x: not x.display_type)
                base_lines = [line._prepare_base_line_for_taxes_computation() for line in order_lines]
                base_lines += order._add_base_lines_for_early_payment_discount()
                AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
                AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
                tax_totals = AccountTax._get_tax_totals_summary(
                    base_lines=base_lines,
                    currency=order.currency_id or order.company_id.currency_id,
                    company=order.company_id,
                )
                # Override tax amounts with custom price_tax from order lines
                custom_tax_total = 0
                base_amount = 0
                for o_line in order_lines:
                    custom_tax_total += round(o_line.price_tax, 0)
                    base_amount += round(o_line.price_subtotal, 0)
                # custom_tax_total = sum(order_lines.mapped('price_tax'))
                # Compute the difference between custom tax and computed tax
                computed_tax = tax_totals.get('tax_amount_currency', 0.0)
                tax_diff = custom_tax_total - computed_tax
                # Update top-level tax amounts
                tax_totals['tax_amount_currency'] = custom_tax_total
                tax_totals['tax_amount'] = custom_tax_total
                tax_totals['base_amount_currency'] = base_amount
                tax_totals['base_amount'] = base_amount
                # Recalculate total_amount = base_amount + tax_amount + cash_rounding
                cash_rounding = tax_totals.get('cash_rounding_base_amount_currency', 0.0)
                cash_rounding_local = tax_totals.get('cash_rounding_base_amount', 0.0)
                tax_totals['total_amount_currency'] = tax_totals['base_amount_currency'] + custom_tax_total + cash_rounding
                tax_totals['total_amount'] = tax_totals['base_amount'] + custom_tax_total + cash_rounding_local
                # Update subtotals and tax groups
                for subtotal in tax_totals.get('subtotals', []):
                    subtotal['tax_amount_currency'] += tax_diff
                    subtotal['tax_amount'] += tax_diff
                    subtotal['base_amount_currency'] = base_amount
                    subtotal['base_amount'] = base_amount
                    for tax_group in subtotal.get('tax_groups', []):
                        tax_group['tax_amount_currency'] += tax_diff
                        tax_group['tax_amount'] += tax_diff
                order.tax_totals = tax_totals
            else:
                super(SaleOrderInherit, order)._compute_tax_totals()

    @api.depends('pricelist_id')
    def compute_check_currency(self):
        for rec in self:
            check_currency_vnd = False
            if rec.pricelist_id and rec.pricelist_id.currency_id:
                currency = rec.pricelist_id.currency_id.name
                if currency == 'VND':
                    check_currency_vnd = True
            rec.sudo().check_currency_vnd = check_currency_vnd

    @api.depends('state', 'misa_status', 'finish_sync_misa')
    def compute_noti_status_misa(self, noti_callback=True):
        lang = self.env.lang or 'en_US'
        for rec in self:
            content = []
            if rec.state not in ['draft', 'sent'] and rec.misa_status not in ['not_synced']:
                if noti_callback:
                    if rec.misa_status in ['synced']:
                        if rec.finish_sync_misa:
                            if lang == 'en_US':
                                content.append('Voucher uploaded to MISA')
                            else:
                                content.append('Đã đưa CT lên Misa')
                        else:
                            if lang == 'en_US':
                                content.append('In queues')
                            else:
                                content.append('Hàng chờ')
                if lang == 'en_US':
                    content.append('Sale Order')
                else:
                    content.append('Đơn đặt hàng')
            if len(content) > 0:
                mess = ' - '.join(content)
                rec.noti_status_misa = '(' + mess + ')'
            else:
                rec.noti_status_misa = ''

    @api.depends('partner_id')
    def _compute_misa_id(self):
        for rec in self:
            misa_id = ''
            if rec.partner_id:
                config = self.env['res.config.settings'].sudo()
                misa_id = config.encode_uuid(str_id='sale_order_' + str(rec.partner_id.id) + str(rec.id))
            rec.misa_id = misa_id

    @api.onchange('payment_term_id')
    def onchange_number_of_days_owed(self):
        for rec in self:
            rec.number_of_days_owed = 0
            if rec.payment_term_id.line_ids:
                data = rec.payment_term_id.line_ids[0]
                rec.number_of_days_owed = data[0].nb_days
    def convert_amount_currency(self, amount= 0):
        return float(amount) * self.exchange_rate if self.exchange_rate else float(amount)


    def sync_misa_sale_order(self, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env[
            'res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        branch_id = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.branch_id', '')
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": []
            }
            err_order = self.filtered(lambda s: s.state != 'sale')
            if err_order:
                mess = '\n'.join(err_order.mapped('name'))
                raise UserError(f'Trạng thái đơn hàng không hợp lệ (Báo giá, Hủy):\n{mess}')
            if self and len(self) > 100:
                raise UserError('Số lượng đơn đặt hàng đồng bộ một lần không được vượt quá 100 đơn.')
            for rec in self:
                posted_date = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                in_reforder = config.get_datetime_format(rec.date_order, TIMEZONE_VN)
                # Chặn k cho đồng bộ nếu chưa hoàn thành các picking
                if rec.picking_ids.filtered(
                        lambda p: p.picking_type_id.code == 'outgoing'
                        and p.state not in ['done', 'cancel']
                    ):
                        raise UserError(
                            f"Không thể đồng bộ SO {rec.name} sang Misa.\n"
                            f"Các phiếu xuất kho chưa hoàn tất!\n"
                            f"Vui lòng xử lý Done/Cancel trước khi đồng bộ."
                        )
                refdate = config.get_datetime_format(datetime.now(), TIMEZONE_VN)
                date_order = config.get_datetime_format(rec.date_order, TIMEZONE_VN)

                if rec.date_pancake:
                    in_reforder = config.get_datetime_format(rec.date_pancake, TIMEZONE_VN)


                error_miss = []
                lang = rec.env.lang or 'en_US'
                # if self.partner_id and not self.partner_id.customer_code:
                #     if lang == 'vi_VN':
                #         error_miss.append('Thiếu thông tin mã khách hàng: \"' + self.partner_id.name + '\"')
                #     else:
                #         error_miss.append('Missing customer code information: \"' + self.partner_id.name + '\"')
                # Mặc định Tỷ giá và Quy đổi phải bằng 1
                if not rec.convert:
                    rec.sudo().convert = 1
                if not rec.exchange_rate:
                    rec.sudo().exchange_rate = 1
                # thiếu thông tin sản phẩm
                if not rec.order_line:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')


                currency_id = rec.currency_id.name if rec.currency_id else 'VND'
                due_day = rec.number_of_days_owed

                # Diễn giải
                journal_memo = rec.pancake_source_id.name if rec.pancake_source_id else ''
                if rec.name_wholesaler:
                    journal_memo += ' - ' + rec.name_wholesaler

                # Địa chỉ giao hàng
                if rec.address_partner_detail:
                    shipping_address = rec.address_partner_detail
                elif rec.shipping_full_address:
                    shipping_address = rec.shipping_full_address
                else:
                    shipping_address = config.get_address(rec.partner_id)

                account_object_code = rec.partner_id.customer_code if rec.partner_id.customer_code else ''
                account_object_name = rec.partner_id.name if rec.partner_id else ''
                if account_object_code == '' and rec.pancake_order_id:
                    account_object_code = rec.pancake_order_id
                if '*' in account_object_name and rec.shipping_full_name and '*' not in rec.shipping_full_name:
                    account_object_name = rec.shipping_full_name

                picking = rec.picking_ids[:1]  # lấy record đầu tiên (recordset), an toàn khi rỗng
                picking = picking and picking[0]

                stock_account = False
                cost_account = False
                stock_code = False
                stock_name = False

                if picking:
                    if picking.picking_type_id:
                        stock_account = picking.picking_type_id.misa_stock_account.code or False
                        cost_account = picking.picking_type_id.misa_cost_account.code or False

                    if picking.location_id and picking.location_id.location_misa_id:
                        stock_code = picking.location_id.location_misa_id.code or False
                        stock_name = picking.location_id.location_misa_id.name or False
                default_customer_id = False
                if rec.pancake_source_id and rec.pancake_source_id.default_customer:
                    default_customer_id = rec.pancake_source_id.default_customer
                if default_customer_id:
                    account_object_name = default_customer_id.name or ''
                    account_object_code = default_customer_id.customer_code or ''
                due_date = False
                if rec.yodee_invoice_date:
                    due_date = rec.yodee_invoice_date + timedelta(days=rec.number_of_days_owed or 0)
                else:
                    base_ref_date = rec.date_pancake or rec.date_order
                    in_reforder = config.get_datetime_format(base_ref_date, TIMEZONE_VN)
                    due_date = base_ref_date + timedelta(days=rec.number_of_days_owed or 0)
                voucher =  {
                            "voucher_type": 13,
                            "org_refid": rec.misa_id,
                            "org_refno": rec.name,
                            "org_reftype_name": "Đơn đặt hàng " + rec.name,

                            "currency_id": currency_id,

                            "refdate": config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                            "due_date": config.get_datetime_format(due_date, TIMEZONE_VN) or in_reforder,
                            "posted_date": config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                            "refno": rec.name,
                            "reftype": 3530,
                            "inv_no": rec.yodee_invoice_code or rec.name,
                            "inv_series": rec.yodee_invoice_number or rec.name,

                            "account_object_name": account_object_name,
                            "account_object_address": config.get_address(rec.partner_id),
                            "account_object_code": account_object_code,
                            "account_object_tax_code": rec.partner_id.vat if rec.partner_id.vat else '',

                            "shipping_address": shipping_address,

                            "discount_type": 1,

                            "exchange_rate": rec.exchange_rate,

                            "journal_memo": journal_memo,

                            "due_day": due_day,
                            "branch_id": branch_id,
                            "include_invoice":0,
                            "total_sale_amount_oc":rec.amount_total,
                            "total_sale_amount": rec.convert_amount_currency(rec.amount_total),
                            "total_amount_oc":rec.amount_total,
                            "total_amount":rec.convert_amount_currency(rec.amount_total),
                            "total_discount_amount_oc":0,
                            "total_vat_amount_oc": rec.tax_totals.get('tax_amount', 0),
                            "total_vat_amount": rec.convert_amount_currency(rec.tax_totals.get('tax_amount', 0)),

                            "is_invoice_exported": False,
                            # "sa_invoice":
                            # {
                            #     "account_object_address": shipping_address,
                            #     # "account_object_bank_account":
                            #     # "account_object_bank_name":
                            #     "account_object_code": account_object_code,
                            #     # "account_object_id": account_object_code,
                            #     "account_object_name": account_object_name,
                            #     # "account_object_tax_code":
                            #     # "account_object_tax_code":
                            #
                            #     "branch_id": branch_id,
                            #     "inv_no": rec.yodee_invoice_code or rec.name,
                            #     "inv_series": rec.yodee_invoice_number or rec.name,
                            #     "inv_template_no": 2,
                            #     "inv_type_id": 1,
                            #     "discount_type": 1,
                            #     'inv_date': config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                            #     "due_date": config.get_datetime_format(due_date, TIMEZONE_VN) or in_reforder,
                            #     # "reftype": 3560,
                            #
                            # },

                            "detail": [],
                            "is_sale_with_outward" : True,
                            "in_outward": {
                                "account_object_code": account_object_code,
                                "account_object_address": shipping_address,
                                "account_object_name": account_object_name,
                                "branch_id": branch_id,
                                "in_reforder": config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                                "posted_date": config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                                "refdate": config.get_datetime_format(rec.yodee_invoice_date, TIMEZONE_VN) or in_reforder,
                                "reftype": 2020,
                                # "reftype_name": "",
                                "refno_finance":rec.name,
                            },
                }

                # Thông tin chi tiết sản phẩm
                total_discount_amount_oc = 0
                delivery_status_arr = []

                if rec.order_line:
                    # Kiểm tra không đồng bộ sản phẩm chưa có trên Misa thì báo lỗi
                    p_non = config.check_product_non_sync_misa(data=rec.order_line.filtered(lambda l: l.product_uom_qty > 0).mapped('product_template_id'), )
                    if p_non:
                        product_names = '\n-'.join(p.display_name for p in p_non)
                        raise UserError(
                            f"Vui lòng đồng bộ sản phẩm trước khi đồng bộ đơn đặt hàng. "
                            f"Sản phẩm chưa được đồng bộ với Misa:\n- {product_names}"
                        )

                    main_convert_rate = rec.convert
                    convert = rec.convert
                    exchange_rate = rec.exchange_rate
                    sort_order = 1
                    # Đồng bộ Misa đơn hàng SL nhu cầu lớn hớn 0
                    for line in rec.order_line.filtered(lambda l: l.product_uom_qty > 0):
                        if line.delivery_status:
                            delivery_status_arr.append(line.delivery_status)
                        if line.product_id:
                            # Discount theo sản phẩm
                            # Thuế
                            discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc = rec.get_discount_vat_misa(
                                data=line, exchange_rate=exchange_rate, convert=convert)
                            total_discount_amount_oc += discount_amount_oc

                            # Tổng tiền
                            amount, amount_oc = rec.get_amount_misa(data=line, exchange_rate=exchange_rate, convert=convert)

                            # Diễn giải
                            is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm

                            # Ưu tiên lấy theo đơn vị đồng bộ từ Misa
                            unit_name = line.product_id.misa_uom_id.name if line.product_id.misa_uom_id else line.product_uom.name

                            # Đồng bộ sản phẩm phải có mã code
                            if not line.product_id.default_code:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                                else:
                                    error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                                continue

                            cost_unit_price = 0
                            moves = line.move_ids.filtered(lambda m: m.state == 'done')

                            valuation_layers = moves.mapped('stock_valuation_layer_ids')

                            total_qty = sum(valuation_layers.mapped('quantity'))
                            total_value = sum(valuation_layers.mapped('value'))

                            if total_qty:
                                cost_unit_price = abs(total_value / total_qty)

                            misa_amount_oc = abs(line.price_subtotal if not line.discount else line.product_uom_qty * line.price_unit)
                            misa_discount_amount_oc = misa_amount_oc - abs(line.price_subtotal)

                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,

                                "account_object_address": shipping_address,
                                "account_object_code": account_object_code,

                                "quantity": line.product_uom_qty,
                                "main_quantity": line.product_uom_qty,

                                "unit_name": line.product_uom.name or '',
                                "main_unit_name": line.product_uom.name or '',

                                "unit_price": abs(line.price_unit),
                                "main_unit_price": abs(line.price_unit),

                                "sort_order": sort_order,
                                "is_promotion": False,

                                "amount": abs(rec.convert_amount_currency(misa_amount_oc)),
                                "amount_oc": misa_amount_oc,

                                "discount_type": discount_type,
                                "discount_rate": discount_rate,  # tỷ lệ chiết khấu từng sản phẩm
                                "discount_rate_voucher": 0,  # tỷ lệ chiết khấu cả đơn hàng
                                "discount_amount": rec.convert_amount_currency(misa_discount_amount_oc),
                                "discount_amount_oc": misa_discount_amount_oc,

                                "vat_rate": vat_rate,
                                "vat_amount": abs(rec.convert_amount_currency(line.price_tax)),

                                "vat_amount_oc": abs(line.price_tax),
                                "other_vat_rate": 0,

                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,

                                'stock_account': stock_account,
                                'cost_account': cost_account,
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "cost_unit_price_finance": cost_unit_price,
                                "cost_amount_finance": cost_unit_price * line.product_uom_qty,

                            }
                            if line.product_id.type == 'service' and line.price_unit < 0:
                                data_sale_line["inventory_item_name"] = line.name or line.product_id.name
                                data_sale_line["description"] = line.name or line.product_id.name
                            if line.price_unit < 0:
                                data_sale_line["is_commercial_abatement"] = True
                            misa_discount_account = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.misa_discount_account', False)
                            if misa_discount_account:
                                data_sale_line["discount_account"] = misa_discount_account
                            if rec.pancake_source_id:
                                data_sale_line["debit_account"] = rec.pancake_source_id.misa_debit_account.code if rec.pancake_source_id.misa_debit_account else ''
                                data_sale_line["credit_account"] = rec.pancake_source_id.misa_credit_account.code if rec.pancake_source_id.misa_credit_account else ''

                            if not rec.pancake_source_id.misa_debit_account or not rec.pancake_source_id.misa_credit_account:
                                raise UserError(
                                    f"Kênh bán hàng '{rec.pancake_source_id.name}' chưa cấu hình Tài khoản nợ/có. "
                                    f"Vui lòng cập nhật trước khi đồng bộ."
                                )

                            if vat_rate == -3:
                                data_sale_line['other_vat_rate'] = 0  # todo required khi với TH thuế khác
                            else:
                                del data_sale_line['other_vat_rate']
                            sort_order += 1
                            if voucher:
                                voucher["detail"].append(data_sale_line)

                            ### Cập nhật chiếu khâu tổng
                            if discount_type:
                                if voucher:
                                    voucher["discount_type"] = discount_type
                if voucher:
                    # Điều khoản thanh toán và Số ngày được nợ
                    payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(
                        data=rec.payment_term_id)
                    if payment_term_id:
                        voucher["payment_term_id"] = payment_term_id
                        voucher["payment_term_code"] = payment_term_code
                        voucher["payment_term_name"] = payment_term_name

                    else:
                        if rec.payment_term_id:
                            if lang == 'vi_VN':
                                error_miss.append(
                                    'Thiếu mã điều khoản thanh toán để đồng bộ với Misa: \"' + payment_term_name + '\"')
                            else:
                                error_miss.append(
                                    'Missing Misa payment term code information: \"' + payment_term_name + '\"')

                    # Diễn giải
                    if rec.note:
                        soup = BeautifulSoup(rec.note, 'html.parser')
                        plain_text = soup.get_text()
                        voucher["journal_memo"] = plain_text

                    # Trạng thái giao hàng
                    # todo
                    if len(delivery_status_arr) > 0:
                        if 'partially_delivered' in delivery_status_arr:
                            voucher["delivered_status"] = 1
                        elif 'not_delivered' in delivery_status_arr:
                            voucher["delivered_status"] = 0
                        else:
                            voucher["delivered_status"] = 2

                if len(error_miss):
                    mess = '\n'.join(error_miss)
                    raise UserError(mess)
                if voucher:
                    body['voucher'].append(voucher)
            # print("len :", len(body['voucher']))
            payload = json.dumps(body, default=str)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            records = self.sudo()
            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    records.misa_status = 'synced'
                else:
                    if data['ErrorCode'] == 'ExpiredToken':
                        records.sync_misa_sale_order(reset_token=True)
                    else:
                        records.misa_status = 'sync_failed'
            else:
                records.misa_status = 'sync_failed'

            IrLogging = rec.env['ir.logging']

            message = 'url: ' + connect_url + '\nheaders\n' + str(headers) + '\ndata\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_sale_order',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(rec._name),
                                     'func': rec.name,
                                     'line': 1})

    def get_delivered_status(self):
        """
        Tình trạng giao hàng
        0 chưa giao
        1 đang giao
        2 đã giao đủ
        (Default = 0)
        """
        self.ensure_one()
        status = 0
        if self.delivery_status:
            if self.delivery_status in ['partial']:
                status = 1
            elif self.delivery_status in ['full']:
                status = 2
        return status

    # def get_status_misa(self):
    #     """
    #     Tình trạng đơn hàng:
    #     0 chưa thực hiện
    #     1 đang thực hiện
    #     2 hoàn thành
    #     3 đã hủy bỏ
    #     (Default = 0)
    #     """
    #     self.ensure_one()
    #     status = 1
    #     # if self.state in ['draft', 'sent']:
    #     #     status = 1
    #     if self.state in ['done']:
    #         status = 2
    #     if self.state in ['cancel']:
    #         status = 3
    #     return status

    def get_discount_vat_misa(self, data, exchange_rate, convert=1):
        """
        discount_type : 0 - không chiết khấu
                        1 - theo mặt hàng
                        2 - theo % hóa đơn
                        3 - số tiền trên tổng hóa đơn
        discount_rate : Tỷ lệ chiết khấu
        discount_amount : Tổng tiền chiết khấu quy đổi (nhân tỷ giá quy đổi)
        discount_amount_oc : Tổng tiền chiết khấu nguyên tệ

        vat_rate : Thuế suất
                    0%: 0
                    5%: 5
                    8%: 8
                    10%: 10
                    KCT: -1
                    KKKNT: -2
                    KHAC: -3
                    other_vat_rate:   Thuế suất khác (bắt buộc phải truyền khi vat_rate = -3)
        vat_amount : Tổng tiền thuế quy đổi
        vat_amount_oc : Tổng tiền thuế nguyên tệ
        """
        discount_type = discount_rate = discount_amount = discount_amount_oc = 0
        if data.discount > 0:
            discount_type = 1
            discount_rate = data.discount
            discount_amount = discount_rate / 100 * data.product_uom_qty * data.price_unit * exchange_rate * convert
            discount_amount_oc = discount_rate / 100 * data.product_uom_qty * data.price_unit
        # if data.pancake_total_discount > 0:
        #     discount_type = 1
        #     discount_rate = (data.pancake_total_discount / data.product_uom_qty) / data.price_unit * 100
        #     discount_amount = data.pancake_total_discount * exchange_rate * convert
        #     discount_amount_oc = data.pancake_total_discount

        vat_rate = vat_amount = vat_amount_oc = 0
        if data.tax_id:
            for tax in data.tax_id:
                vat_rate += tax.amount
        if vat_rate not in [0, 5, 8, 10, -1, -2, -3]:
            raise UserError(
                _("The tax for product \'%s\' is invalid for synchronization with Misa.", data.product_id.name))
        if vat_rate:
            vat_amount = vat_rate / 100 * data.product_uom_qty * data.price_unit * exchange_rate * convert * (
                    1 - (discount_rate / 100))
            vat_amount_oc = vat_rate / 100 * data.product_uom_qty * data.price_unit * (1 - (discount_rate / 100))

        return discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc

    def get_amount_misa(self, data, exchange_rate, convert=1):
        amount = amount_oc = 0
        if data and exchange_rate:
            amount = data.product_uom_qty * data.price_unit * exchange_rate * convert
            amount_oc = data.product_uom_qty * data.price_unit
        return amount, amount_oc

    @api.model
    def cron_sync_misa_sale_orders(self, limit=1000):
        domain = [
            "&",
            "&",
            "&",
            "&",
            "&",
            "&",
            ("state", "not in", ["cancel"]),
            "|",
            "&", ("date_pancake", ">=", "2025-12-31 17:00:00"), ("date_pancake", "<=", "2026-04-30 16:59:59"),
            "&", "&", ("validity_date", ">=", "2026-01-01"), ("validity_date", "<=", "2026-04-30"), ("date_pancake", "=", False),
            ("locked", "=", False),
            ("state", "=", "sale"),
            ("picking_ids", "!=", False),
            ("delivery_status", "=", "full"),
            ("pancake_source_id.misa_debit_account", "!=", False)
        ]
        orders = self.env['sale.order'].sudo().search(domain, limit=limit)
        IrLogging = self.env['ir.logging'].sudo()
        BATCH_SIZE = 100
        for i in range(0, len(orders), BATCH_SIZE):
            batch = orders[i:i + BATCH_SIZE]
            try:
                batch.sync_misa_sale_order()
            except Exception as e:
                IrLogging.create({
                    'name': 'cron_sync_misa_sale_orders',
                    'type': 'server',
                    'message': f'Error syncing batch {batch.mapped("name")}: {str(e)}',
                    'path': 'sale.order',
                    'func': 'cron_sync_misa_sale_orders',
                    'line': 1,
                })
                continue
            synced = batch.filtered(lambda o: o.misa_status == 'synced')
            if synced:
                synced.sudo().write({'locked': True})

    def action_cancel(self):
        for rec in self:
            # if rec.misa_status in ['synced', 'sync_failed']:
            #     raise UserError("Đơn hàng đã đồng bộ Misa, không thể hủy")
            return super(SaleOrderInherit, self).action_cancel()

    def sync_misa_orders(self):
        for rec in self:
            if not rec.pancake_source_id:
                raise UserError(f'Đơn hàng {rec.name} chưa điền thông tin \'Kênh bán hàng\' nên không thể đồng bộ')
            elif rec.state not in ['sale']:
                raise UserError(f'Trang thái đơn hàng {rec.name} chưa được xác nhận nên không thể đồng bộ')
            else:
                rec.sync_misa_sale_order()
        return True

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_amounts(self):
        res = super(SaleOrderInherit, self)._compute_amounts()
        for order in self:
            total_tax_order = 0
            amount_untaxed = 0
            for line in order.order_line:
                total_tax_order += round(line.price_tax, 0)
                amount_untaxed += round(line.price_subtotal, 0)
            order.amount_tax = total_tax_order
            order.amount_untaxed = amount_untaxed
            order.amount_total = amount_untaxed + total_tax_order
        return res


