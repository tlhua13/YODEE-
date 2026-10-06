from odoo import fields, models, api, _
import requests
import json
from odoo.exceptions import UserError
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    misa_status = fields.Selection([('not_synced', 'Unsynchronized'),
                                    ('synced', 'Synchronized'),
                                    ('sync_failed', 'Synchronization Failed'),
                                    ], string='Misa Status', default='not_synced', copy=False)

    exchange_rate = fields.Float(string="Exchange Rate", default=1, tracking=True)  # Tỷ giá
    convert = fields.Float(string='Convert', default=1, tracking=True)  # Quy đổi

    check_currency_vnd = fields.Boolean(string='Check Currency VND', compute='compute_check_currency')

    def _get_destination_location(self):
        self.ensure_one()
        open_picking = self.picking_ids.filtered(
            lambda p: p.picking_type_id == self.picking_type_id and p.state not in ('done', 'cancel')
        ).sorted('id', reverse=True)[:1]
        if open_picking:
            return open_picking.location_dest_id.id
        return super()._get_destination_location()

    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'company_id', 'currency_id')
    def _amount_all(self):
        for order in self:
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            amount_untaxed = round(sum(order_lines.mapped('price_subtotal')), 2)
            amount_tax = round(sum(order_lines.mapped('price_tax')), 2)
            order.amount_untaxed = amount_untaxed
            order.amount_tax = amount_tax
            order.amount_total = amount_untaxed + amount_tax
            order.amount_total_cc = order.amount_total / order.currency_rate if order.currency_rate else order.amount_total

    @api.depends_context('lang')
    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'currency_id', 'company_id')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if not order.tax_totals:
                continue
            tax_totals = order.tax_totals
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            base_amount = round(sum(order_lines.mapped('price_subtotal')), 2)
            tax_amount = round(sum(order_lines.mapped('price_tax')), 2)

            # Update top-level totals
            tax_totals['base_amount_currency'] = base_amount
            tax_totals['base_amount'] = base_amount
            tax_totals['tax_amount_currency'] = tax_amount
            tax_totals['tax_amount'] = tax_amount
            tax_totals['total_amount_currency'] = base_amount + tax_amount
            tax_totals['total_amount'] = base_amount + tax_amount

            # Update subtotals and tax groups using price_subtotal and price_tax from lines
            for subtotal in tax_totals.get('subtotals', []):
                subtotal_base = 0.0
                subtotal_tax = 0.0
                has_tax_groups = False
                for tax_group in subtotal.get('tax_groups', []):
                    has_tax_groups = True
                    involved_tax_ids = tax_group.get('involved_tax_ids', [])
                    group_base = round(sum(
                        line.price_subtotal for line in order_lines
                        if any(tax.id in involved_tax_ids for tax in line.taxes_id)
                    ), 2)
                    group_tax = round(sum(
                        line.price_tax for line in order_lines
                        if any(tax.id in involved_tax_ids for tax in line.taxes_id)
                    ), 2)
                    tax_group['base_amount_currency'] = group_base
                    tax_group['base_amount'] = group_base
                    tax_group['tax_amount_currency'] = group_tax
                    tax_group['tax_amount'] = group_tax
                    subtotal_base += group_base
                    subtotal_tax += group_tax
                if not has_tax_groups:
                    subtotal_base = base_amount
                    subtotal_tax = tax_amount
                subtotal['base_amount_currency'] = subtotal_base
                subtotal['base_amount'] = subtotal_base
                subtotal['tax_amount_currency'] = subtotal_tax
                subtotal['tax_amount'] = subtotal_tax

            order.tax_totals = tax_totals

    number_of_days_owed = fields.Integer(string='Number of days owed')

    is_buying_cost = fields.Boolean(string='Is Buying Cost', compute='compute_is_buying_cost', store=True)

    include_invoice_misa = fields.Selection([
        ('0', 'Invoice not included'),
        ('1', 'Invoice included'),
        ('2', 'No bill'),
    ], string='Include Invoice', default='0')

    noti_status_misa = fields.Char(string='Noti Status', compute='compute_noti_status_misa')

    finish_sync_misa = fields.Boolean(string='Finish Sync Misa', default=False, copy=False)

    # Đơn mua hàng
    misa_id = fields.Char(string='Misa ID', compute='_compute_misa_id', store=True)
    # Chứng từ mua hàng
    misa_pu_invoice_id = fields.Char(string='Misa PU Invoice ID', compute='_compute_misa_pu_invoice_id', store=True)

    invoice_purchase_number = fields.Char(string='Invoice Purchase Number')

    @api.depends('partner_id')
    def _compute_misa_id(self):
        for rec in self:
            misa_id = ''
            if rec.partner_id:
                config = self.env['res.config.settings'].sudo()
                misa_id = config.encode_uuid(str_id='purchase_order_' + str(rec.partner_id.id) + str(rec.id))
            rec.misa_id = misa_id

    @api.depends('partner_id')
    def _compute_misa_pu_invoice_id(self):
        for rec in self:
            misa_pu_invoice_id = ''
            if rec.partner_id:
                config = self.env['res.config.settings'].sudo()
                misa_pu_invoice_id = config.encode_uuid(str_id='pu_invoice_' + str(rec.partner_id.id) + str(rec.id))
            rec.misa_pu_invoice_id = misa_pu_invoice_id

    @api.depends('order_line', 'order_line.product_id')
    def compute_is_buying_cost(self):
        for rec in self:
            rec.is_buying_cost = any(
                line.product_id and (line.product_id.type == 'service'or line.product_id.misa_features == 'service')
                for line in rec.order_line
            )

    @api.onchange('payment_term_id')
    def onchange_number_of_days_owed(self):
        for rec in self:
            rec.number_of_days_owed = 0
            if rec.payment_term_id.line_ids:
                data = rec.payment_term_id.line_ids[0]
                rec.number_of_days_owed = data[0].nb_days

    @api.depends('is_buying_cost', 'state', 'misa_status', 'finish_sync_misa')
    def compute_noti_status_misa(self, noti_callback=True):
        lang = self.env.lang or 'en_US'
        for rec in self:
            content = []
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
            if rec.state not in ['draft', 'sent'] and rec.misa_status not in ['not_synced']:
                # if rec.is_buying_cost:
                #     if lang == 'en_US':
                #         content.append('Service Purchase Invoice')
                #     else:
                #         content.append('Mua hàng dịch vụ')
                # else:
                if lang == 'en_US':
                    content.append('Purchase Order')
                else:
                    content.append('Đơn mua hàng')

            if len(content) > 0:
                mess = ' - '.join(content)
                rec.noti_status_misa = '(' + mess + ')'
            else:
                rec.noti_status_misa = ''

    @api.depends('currency_id')
    def compute_check_currency(self):
        for rec in self:
            rec.check_currency_vnd = bool(rec.currency_id and rec.currency_id.name == 'VND')

    @api.onchange('currency_id')
    def onchange_currency_id(self):
        for rec in self:
            rec.exchange_rate = 1
            rec.convert = 1

    def sync_misa_purchase_order(self, reset_token=False):
        # self.check_sync_misa_product_type()
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        branch_id = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.branch_id', '')
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            refdate = config.get_datetime_format(self.date_approve, TIMEZONE_VN)
            receive_date = config.get_datetime_format(self.date_planned, TIMEZONE_VN)

            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }

            error_miss = []
            lang = self.env.lang or 'en_US'
            # Mặc định Tỷ giá và Quy đổi phải bằng 1
            if not self.convert:
                self.sudo().convert = 1
            if not self.exchange_rate:
                self.sudo().exchange_rate = 1
            # Kiểm tra mã khách hàng
            if self.partner_id and not self.partner_id.customer_code:
                if lang == 'vi_VN':
                    error_miss.append('Thiếu thông tin mã nhà cung cấp: \"' + self.partner_id.name + '\"')
                else:
                    error_miss.append('Missing supply code information: \"' + self.partner_id.name + '\"')
            non_res_partner = config.check_res_partner_non_sync_misa(data=self)
            if non_res_partner:
                mess = ','.join(res_partner.name for res_partner in non_res_partner)
                raise UserError(f'Thông tin liên hệ {mess} từ Misa chưa đồng bộ về Odoo.\nVui lòng chờ thông tin đồng bộ về Odoo trước khi đồng bộ đơn đặt hàng.')

            # thiếu thông tin sản phẩm
            if not self.order_line:
                if lang == 'vi_VN':
                    error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                else:
                    error_miss.append('Missing products information')
            voucher_type_purchase = 21
            employee_code, employee_name = config.get_employee_name(data=self.user_id)
            due_day = self.number_of_days_owed

            account_object_code = self.partner_id.customer_code if self.partner_id.customer_code else ''
            account_object_name = self.partner_id.name if self.partner_id else ''

            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": [
                    {
                        "voucher_type": voucher_type_purchase,

                        "org_refid": self.misa_id,
                        "org_refno": self.name,
                        "org_reftype": 301,
                        "org_reftype_name": "Đơn đặt hàng " + self.name,

                        "currency_id": self.currency_id.name if self.currency_id else 'VND',

                        "refdate": refdate,
                        "receive_date": receive_date,
                        "refno": self.name,

                        "account_object_id": self.partner_id.misa_id if self.partner_id  and self.partner_id.misa_id else  '',
                        "account_object_code": account_object_code,
                        "account_object_name": account_object_name,
                        "account_object_address": config.get_address(self.partner_id),
                        "account_object_tax_code": self.partner_id.vat if self.partner_id.vat else '',

                        # "receive_address": self.get_receive_address(),
                        # "receiver": "",

                        # "employee_code": employee_code,
                        # "employee_name": employee_name,

                        'discount_type': 0,

                        "exchange_rate": self.exchange_rate,

                        "journal_memo": "",

                        "reftype": 301,
                        "due_day": due_day,
                        "branch_id": branch_id,
                        "status": self.get_status_misa(),
                        "total_amount_oc": 0,
                        "total_amount": 0,
                        "total_vat_amount_oc": 0,
                        "total_vat_amount": 0,
                        "total_discount_amount_oc": 0,
                        "total_discount_amount": 0,

                        "detail": []
                    }],
            }

            # Thông tin chi tiết sản phẩm
            total_amount_oc = 0
            total_amount = 0
            total_vat_amount_oc = 0
            total_vat_amount = 0
            total_discount_amount_oc = 0
            total_discount_amount = 0
            if self.order_line:
                # Kiểm tra không đồng bộ sản phẩm chưa có trên Misa thì báo lỗi
                p_non = config.check_product_non_sync_misa(data=self.order_line.mapped('product_id'))
                if p_non:
                    product_names = '\n-'.join(p.display_name for p in p_non)
                    raise UserError(
                        f"Vui lòng đồng bộ sản phẩm trước khi đồng bộ đơn mua hàng. "
                        f"Sản phẩm chưa được đồng bộ với Misa:\n- {product_names}"
                    )
                main_convert_rate = self.convert
                convert = self.convert
                exchange_rate = self.exchange_rate
                sort_order = 1
                for line in self.order_line:
                    if line.product_id:
                        # Discount theo sản phẩm
                        discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc = self.get_discount_vat_misa(data=line, exchange_rate=exchange_rate, convert=convert)
                        total_discount_amount += discount_amount
                        total_discount_amount_oc += discount_amount_oc
                        total_vat_amount += vat_amount
                        total_vat_amount_oc += vat_amount_oc

                        # Thuế
                        # vat_rate, vat_amount, vat_amount_oc = self.get_vat_amount_misa(data=line, exchange_rate=exchange_rate, convert=convert)

                        # Tổng tiền
                        amount, amount_oc = self.get_amount_misa(data=line, exchange_rate=exchange_rate, convert=convert)
                        total_amount += amount
                        total_amount_oc += amount_oc

                        # Diễn giải
                        is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm

                        if not line.product_id.default_code:
                            if lang == 'vi_VN':
                                error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                            else:
                                error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                            continue
                        data_sale_line = {
                            "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                            "inventory_item_name": line.product_id.name if line.product_id.name else '',
                            "description": line.product_id.name if line.product_id.name else '',

                            "account_object_id": self.partner_id.misa_id if self.partner_id  and self.partner_id.misa_id else  '',
                            "account_object_code": account_object_code,
                            "account_object_name": account_object_name,

                            "quantity": line.product_uom_qty,
                            "main_quantity": line.product_uom_qty,

                            "unit_name": line.product_uom.name if line.product_uom else '',
                            "unit_price": line.price_unit,

                            "main_unit_name": line.product_uom.name if line.product_uom else '',
                            "main_unit_price": line.price_unit,

                            "sort_order": sort_order,
                            "is_promotion": False,

                            "amount": amount,
                            "amount_oc": amount_oc,

                            "discount_type": discount_type,
                            # "discount_rate": discount_rate,  # tỷ lệ chiết khấu từng sản phẩm
                            # "discount_rate_voucher": 0,  # tỷ lệ chiết khấu cả đơn hàng
                            # "discount_amount": discount_amount,
                            # "discount_amount_oc": discount_amount_oc,

                            "vat_rate": vat_rate,
                            "vat_amount": vat_amount,
                            "vat_amount_oc": vat_amount_oc,
                            "other_vat_rate": 0,

                            "exchange_rate_operator": "*",
                            "main_convert_rate": main_convert_rate,
                            "exchange_rate": exchange_rate,
                            "currency_id": self.currency_id.name if self.currency_id else 'VND',

                            "status": self.get_status_misa(),
                        }

                        if vat_rate == -3:
                            data_sale_line['other_vat_rate'] = 0  # todo required khi với TH thuế khác
                        else:
                            del data_sale_line['other_vat_rate']
                        sort_order += 1
                        if body["voucher"][0]:
                            detail = body["voucher"][0]
                            detail["detail"].append(data_sale_line)

                        ### Cập nhật chiếu khâu tổng
                        if discount_type:
                            if body["voucher"][0]:
                                detail["discount_type"] = discount_type

            if total_vat_amount > 0:
                ### Tính thuế thì đính kèm hóa đơn
                self.sudo().include_invoice_misa = '1'

            if body["voucher"][0]:
                for data in body["voucher"]:
                    # Update đơn mua hàng
                    if data['voucher_type'] == voucher_type_purchase:
                        detail = data
                        # Tính tổng chi phí
                        detail['total_amount_oc'] = total_amount_oc
                        detail['total_amount'] = total_amount
                        detail['total_vat_amount_oc'] = total_vat_amount_oc
                        detail['total_vat_amount'] = total_vat_amount
                        detail['total_discount_amount_oc'] = total_discount_amount_oc
                        detail['total_discount_amount'] = total_discount_amount

                        # Tính giảm giá tổng đơn đơn
                        if total_discount_amount_oc > 0:
                            total_base_price = 0
                            for line in self.order_line:
                                base_price = line._get_pricelist_price_before_discount()
                                total_base_price += base_price
                            if total_base_price > 0:
                                detail["discount_rate_voucher"] = round(total_discount_amount_oc / total_base_price * 100, 2)

                        # Điều khoản thanh toán và Số ngày được nợ
                        payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(data=self.payment_term_id)
                        if payment_term_id:
                            detail["payment_term_id"] = payment_term_id
                            detail["payment_term_code"] = payment_term_code
                            detail["payment_term_name"] = payment_term_name
                        else:
                            if self.payment_term_id:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã điều khoản thanh toán để đồng bộ với Misa: \"' + payment_term_name + '\"')
                                else:
                                    error_miss.append('Missing Misa payment term code information: \"' + payment_term_name + '\"')
                        # Diễn giải
                        if self.notes:
                            soup = BeautifulSoup(self.notes, 'html.parser')
                            plain_text = soup.get_text()
                            detail["journal_memo"] = plain_text

            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    self.sudo().misa_status = 'synced'
                else:
                    # Token hết hạn
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        self.sync_misa_purchase_order(reset_token=True)
                    else:
                        self.sudo().misa_status = 'sync_failed'
            else:
                self.sudo().misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']

            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_purchase_order',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self._name),
                                     'func': self.name,
                                     'line': 1})

    def sync_misa_purchase_invoice_service(self, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()
            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            refdate = config.get_datetime_format(self.date_approve, TIMEZONE_VN)
            created_date = config.get_datetime_format(self.create_date, TIMEZONE_VN)
            write_date = config.get_datetime_format(self.write_date, TIMEZONE_VN)
            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }

            error_miss = []
            lang = self.env.lang or 'en_US'
            # Mặc định Tỷ giá và Quy đổi phải bằng 1
            if not self.convert:
                self.sudo().convert = 1
            if not self.exchange_rate:
                self.sudo().exchange_rate = 1
            # Kiểm tra mã khách hàng
            if self.partner_id and not self.partner_id.customer_code:
                if lang == 'vi_VN':
                    error_miss.append('Thiếu thông tin mã khách hàng: \"' + self.partner_id.name + '\"')
                else:
                    error_miss.append('Missing customer code information: \"' + self.partner_id.name + '\"')

            voucher_type = 17
            account_object_name = self.partner_id.name if self.partner_id else ''
            account_object_address = config.get_address(self.partner_id)
            account_object_code = self.partner_id.customer_code if self.partner_id.customer_code else ''
            account_object_tax_code = self.partner_id.vat if self.partner_id.vat else ''
            employee_code, employee_name = config.get_employee_name(data=self.user_id)
            due_time = self.number_of_days_owed
            include_invoice = int(self.include_invoice_misa) if self.include_invoice_misa else 0
            due_date = ""
            if due_time > 0 and refdate:
                new_date = self.date_approve + timedelta(days=due_time)
                due_date = config.get_datetime_format(new_date, TIMEZONE_VN)

            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": [
                    {
                        "voucher_type": voucher_type,
                        "include_invoice": include_invoice,
                        "is_freight_service": True,  # Là chi phí mua hàng

                        "org_refid": self.misa_pu_invoice_id,
                        "org_refno": "Chứng từ mua dịch vụ " + self.name,
                        "org_reftype": self.get_reftype_pu_invoice_misa(),
                        "org_reftype_name": "Chứng từ mua dịch vụ " + self.name,

                        "currency_id": self.currency_id.name if self.currency_id else 'VND',

                        "refdate": refdate,
                        "refno": self.name,

                        "posted_date": refdate,

                        "account_object_name": account_object_name,
                        "account_object_address": account_object_address,
                        "account_object_code": account_object_code,
                        "account_object_tax_code": account_object_tax_code,

                        # "receive_address": config.get_address(self.partner_id),
                        # "receiver": "",

                        # "employee_code": employee_code,
                        # "employee_name": employee_name,


                        'discount_type': 0,

                        "exchange_rate": self.exchange_rate,

                        "journal_memo": "",

                        "reftype": self.get_reftype_pu_invoice_misa(),
                        "branch_id": "",
                        "status": self.get_status_misa(),

                        "due_time": due_time,
                        "due_date": due_date,

                        "total_amount_oc": 0,
                        "total_amount": 0,
                        "total_vat_amount_oc": 0,
                        "total_vat_amount": 0,
                        "total_discount_amount_oc": 0,
                        "total_discount_amount": 0,

                        "detail": []
                    }],
            }

            # Thông tin chi tiết sản phẩm
            total_amount_oc = 0
            total_amount = 0
            total_vat_amount_oc = 0
            total_vat_amount = 0
            total_discount_amount_oc = 0
            total_discount_amount = 0
            if self.order_line:
                main_convert_rate = self.convert
                convert = self.convert
                exchange_rate = self.exchange_rate
                sort_order = 1
                for line in self.order_line:
                    if line.product_id:
                        # Discount theo sản phẩm
                        discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc = self.get_discount_vat_misa(data=line, exchange_rate=exchange_rate, convert=convert)
                        total_discount_amount += discount_amount
                        total_discount_amount_oc += discount_amount_oc
                        total_vat_amount += vat_amount
                        total_vat_amount_oc += vat_amount_oc

                        # Thuế
                        # vat_rate, vat_amount, vat_amount_oc = self.get_vat_amount_misa(data=line, exchange_rate=exchange_rate, convert=convert)

                        # Tổng tiền
                        amount, amount_oc = self.get_amount_misa(data=line, exchange_rate=exchange_rate, convert=convert)
                        total_amount += amount
                        total_amount_oc += amount_oc

                        # Diễn giải
                        is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm

                        if not line.product_id.default_code:
                            if lang == 'vi_VN':
                                error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                            else:
                                error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                            continue
                        # TK kho/Chí phi + TK Công nợ
                        debit_account = line.misa_account_inventory.code if line.misa_account_inventory else False
                        credit_account = line.misa_account_receivable.code if line.misa_account_receivable else False

                        data_sale_line = {
                            "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                            "inventory_item_name": line.product_id.name if line.product_id.name else '',
                            "description": line.product_id.name if line.product_id.name else '',
                            "is_description": is_description,

                            "quantity": line.product_uom_qty,
                            "main_quantity": line.product_uom_qty,

                            "unit_name": line.product_uom.name if line.product_uom else '',
                            "unit_price": line.price_unit,

                            "main_unit_name": line.product_uom.name if line.product_uom else '',
                            "main_unit_price": line.price_unit,

                            "sort_order": sort_order,
                            "is_promotion": False,

                            "account_object_name": account_object_name,
                            "account_object_code": account_object_code,
                            "account_object_tax_code": account_object_tax_code,

                            "amount": amount,
                            "amount_oc": amount_oc,

                            "discount_type": discount_type,
                            # "discount_rate": discount_rate,  # tỷ lệ chiết khấu từng sản phẩm
                            # "discount_rate_voucher": 0,  # tỷ lệ chiết khấu cả đơn hàng
                            # "discount_amount": discount_amount,
                            # "discount_amount_oc": discount_amount_oc,

                            "vat_rate": vat_rate,
                            "vat_amount": vat_amount,
                            "vat_amount_oc": vat_amount_oc,
                            "other_vat_rate": 0,

                            "exchange_rate_operator": "*",
                            "main_convert_rate": main_convert_rate,
                            "exchange_rate": exchange_rate,
                            "currency_id": self.currency_id.name if self.currency_id else 'VND',

                            "status": self.get_status_misa(),

                            "debit_account": debit_account,
                            "credit_account": credit_account,
                        }

                        if vat_rate == -3:
                            data_sale_line['other_vat_rate'] = 0  # todo required khi với TH thuế khác
                        else:
                            del data_sale_line['other_vat_rate']
                        sort_order += 1
                        if body["voucher"][0]:
                            detail = body["voucher"][0]
                            detail["detail"].append(data_sale_line)

                        ### Cập nhật chiếu khâu tổng
                        if discount_type:
                            if body["voucher"][0]:
                                detail["discount_type"] = discount_type

            if total_vat_amount > 0:
                ### Tính thuế thì đính kèm hóa đơn
                self.sudo().include_invoice_misa = '1'
            if body["voucher"][0]:
                for data in body["voucher"]:
                    # Update đơn mua hàng
                    if data['voucher_type'] == voucher_type:
                        detail = data
                        # Tính tổng chi phí
                        detail['total_amount_oc'] = total_amount_oc
                        detail['total_amount'] = total_amount
                        detail['total_vat_amount_oc'] = total_vat_amount_oc
                        detail['total_vat_amount'] = total_vat_amount
                        detail['total_discount_amount_oc'] = total_discount_amount_oc
                        detail['total_discount_amount'] = total_discount_amount

                        # Tính giảm giá tổng đơn đơn
                        if total_discount_amount_oc > 0:
                            total_base_price = 0
                            for line in self.order_line:
                                base_price = line._get_pricelist_price_before_discount()
                                total_base_price += base_price
                            if total_base_price > 0:
                                detail["discount_rate_voucher"] = round(total_discount_amount_oc / total_base_price * 100, 2)

                        # Thêm thông tin người bán lên Misa nếu có mã Misa
                        if self.user_id and self.user_id.employee_ids:
                            employee = self.user_id.employee_ids[0]
                            if employee.employee_code_misa:
                                detail["employee_code"] = employee.employee_code_misa

                        # Điều khoản thanh toán và Số ngày được nợ
                        payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(data=self.payment_term_id)
                        if payment_term_id:
                            detail["payment_term_id"] = payment_term_id
                            detail["payment_term_code"] = payment_term_code
                            detail["payment_term_name"] = payment_term_name
                        else:
                            if self.payment_term_id:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã điều khoản thanh toán để đồng bộ với Misa: \"' + payment_term_name + '\"')
                                else:
                                    error_miss.append('Missing Misa payment term code information: \"' + payment_term_name + '\"')

                        # Diễn giải
                        if self.notes:
                            soup = BeautifulSoup(self.notes, 'html.parser')
                            plain_text = soup.get_text()
                            detail["journal_memo"] = plain_text

            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    self.sudo().misa_status = 'synced'
                else:
                    # Token hết hạn
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        self.sync_misa_purchase_invoice_service(reset_token=True)
                    else:
                        self.sudo().misa_status = 'sync_failed'
            else:
                self.sudo().misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']

            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_purchase_invoice_service',
                                     'type': 'server',
                                     'message': message,
                                     'path': 'path',
                                     'func': 'pu_invoice_' + self.name,
                                     'line': 1})

    def get_amount_misa(self, data, exchange_rate, convert=1):
        amount = amount_oc = 0
        if data and exchange_rate:
            amount = data.price_subtotal * exchange_rate * convert
            amount_oc = data.price_subtotal
        return amount, amount_oc

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
        # if data.discount > 0:
        #     discount_type = 1
        #     discount_rate = data.discount
        #     discount_amount = discount_rate / 100 * data.product_uom_qty * data.price_unit * exchange_rate * convert
        #     discount_amount_oc = discount_rate / 100 * data.product_uom_qty * data.price_unit

        vat_rate = vat_amount = vat_amount_oc = 0
        if data.taxes_id:
            for tax in data.taxes_id:
                vat_rate += tax.amount
        if vat_rate not in [0, 5, 8, 10, -1, -2, -3]:
            raise UserError(_("The tax for product \'%s\' is invalid for synchronization with Misa.", data.product_id.name))
        if vat_rate:
            vat_amount = vat_rate / 100 * data.product_uom_qty * data.price_unit * exchange_rate * convert * (1 - (discount_rate / 100))
            vat_amount_oc = vat_rate / 100 * data.product_uom_qty * data.price_unit * (1 - (discount_rate / 100))

        return discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc


    def get_status_misa(self):
        """
        Tình trạng đơn hàng:   1: Chưa thực hiện;
                               2: Đang thực hiện;
                               3: Hoàn thành
                               4: Hủy bỏ
        """
        self.ensure_one()
        status = 1
        # if self.state in ['done']:
        #     status = 3
        if self.state in ['cancel']:
            status = 4
        return status

    def get_reftype_pu_invoice_misa(self):
        """
        Chứng từ mua hàng bao gồm hóa đơn (mặc định chưa thanh toán)
            302: Mua hàng trong nước nhập kho chưa thanh toán
            312: Mua hàng trong nước không qua kho chưa thanh toán
            318: Mua hàng nhập khẩu nhập kho chưa thanh toán

        * Hàng nhập khẩu luôn lưu kho
        * Hàng trong nước có lưu kho hoặc không


        Chứng từ mua hàng dịch vụ (mặc định chưa thanh toán)
            330: Chứng từ mua dịch vụ chưa thanh toán
            331: Chứng từ mua dịch vụ - Tiền mặt
            332: Chứng từ mua dịch vụ - Ủy nhiệm chi
            333: Chứng từ mua dịch vụ - Chuyển khoản
            334: Chứng từ mua dịch vụ - Séc tiền mặt
        """
        reftype = 302
        self.ensure_one()
        if self.is_buying_cost:
            reftype = 330
        if self.purchase_order_type == 'foreign':
            reftype = 318
        return reftype

    @api.depends('picking_type_id')
    def _compute_dest_address_id_new(self):
        for rec in self:
            address = False
            if rec.picking_type_id and rec.picking_type_id.location_address_id:
                address = rec.picking_type_id.location_address_id.id
            rec.dest_address_id = address

    def action_set_qty_to_received(self):
        line_ids = self.mapped('order_line').ids
        if line_ids:
            self.env.cr.execute("""
                UPDATE purchase_order_line
                SET product_qty = qty_received
                WHERE id IN %s
                  AND product_qty != qty_received
                  AND qty_received > 0
            """, (tuple(line_ids),))
            self.mapped('order_line').invalidate_recordset(['product_qty'])

    def sync_misa_purchase_order_list(self):
        for rec in self:
            if rec.state not in ['purchase']:
                raise UserError(f'Đơn {rec.name} chưa được xác nhận là "Đơn mua hàng" nên không thể đồng bộ')
            else:
                rec.sync_misa_purchase_order()
        return True

