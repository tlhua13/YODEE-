import pytz

from odoo import api, fields, models, _
import requests
import json
from odoo.exceptions import UserError
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from odoo import api, fields, models

class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'

    misa_status_related = fields.Selection([('not_synced', 'Unsynchronized'),
                                    ('synced', 'Synchronized'),
                                    ('sync_failed', 'Synchronization Failed'),
                                    ], string='Misa Status',compute='_compute_misa_status_related',store=True)
    misa_status = fields.Selection([('not_synced', 'Unsynchronized'),
                                    ('synced', 'Synchronized'),
                                    ('sync_failed', 'Synchronization Failed'),
                                    ], string='Misa Status', default='not_synced', copy=False)
    include_invoice_misa = fields.Selection([
        ('0', 'Invoice not included'),
        ('1', 'Invoice included'),
        ('2', 'No bill'),
    ], string='Include Invoice', default='0', copy=False)

    misa_id = fields.Char(string='Misa ID', compute='_compute_misa_id', store=True)

    noti_status_misa = fields.Char(string='Noti Status', compute='compute_noti_status_misa')
    finish_sync_misa = fields.Boolean(string='Finish Sync Misa', default=False, copy=False)

    is_misa_pu_invoice = fields.Boolean(default=False, copy=False)
    is_misa_stock_in = fields.Boolean(default=False, copy=False)
    is_misa_stock_out = fields.Boolean(default=False, copy=False)
    is_misa_stock_internal = fields.Boolean(default=False, copy=False)
    is_misa_return = fields.Boolean(default=False, copy=False)
    is_misa_stock_other_in = fields.Boolean(default=False, copy=False)
    is_misa_stock_other_out = fields.Boolean(default=False, copy=False)
    transporter = fields.Many2one('res.users', string='Transporter')
    em_transporter = fields.Many2one('hr.employee', string='Transporter')
    origin_misa = fields.Char(string='Số chứng từ BH', copy=False)

    name_wholesaler = fields.Char(string='Wholesaler Customer', related='partner_id.name_wholesaler', store=True)
    is_wholesaler = fields.Boolean(string='Is Wholesale Customer', related='partner_id.is_wholesaler', store=True)
    tracking_id = fields.Char(string='Tracking ID', related='sale_id.tracking_id', store=True)
    total_quantity = fields.Float(
        string="Total Quantity",
        compute="_compute_total_quantity",
        store=False
    )
    pancake_status = fields.Selection(
        related='sale_id.pancake_status',
        string='Pancake Status',
        store=True,
        readonly=True
    )
    yodee_invoice_code = fields.Char(string='Invoice code', related='sale_id.yodee_invoice_code', store=True)
    yodee_invoice_date = fields.Date(string='Invoice date', related='sale_id.yodee_invoice_date', store=True)
    done_do_can_create_backorder = fields.Boolean(string="Có thể tạo backorder",
                                                  compute="_compute_done_do_can_create_backorder")

    def _compute_done_do_can_create_backorder(self):
        for rec in self:
            if rec.state == 'done':
                rec.done_do_can_create_backorder = True if rec._check_backorder() else False
            else:
                rec.done_do_can_create_backorder = False

    @api.depends('partner_id')
    def _compute_misa_id(self):
        for rec in self:
            config = self.env['res.config.settings'].sudo()
            if rec.partner_id:
                misa_id = config.encode_uuid(str_id='stock_picking_' + str(rec.partner_id.id) + str(rec.id))
            else:
                misa_id = config.encode_uuid(str_id='stock_picking_' + str(rec.id))
            rec.misa_id = misa_id

    @api.depends('state', 'misa_status', 'finish_sync_misa')
    def compute_noti_status_misa(self, noti_callback=True):
        lang = self.env.lang or 'en_US'
        for rec in self:
            mess = []
            if rec.state not in ['draft', 'sent'] and rec.misa_status not in ['not_synced']:
                if noti_callback:
                    if rec.misa_status in ['synced']:
                        if rec.finish_sync_misa:
                            if lang == 'en_US':
                                mess.append('Voucher uploaded to MISA')
                            else:
                                mess.append('Đã đưa CT lên Misa')
                        else:
                            if lang == 'en_US':
                                mess.append('In queues')
                            else:
                                mess.append('Hàng chờ')
                ### Chứng từ mua hàng nhập kho kèm hoá đơn
                if rec.is_misa_pu_invoice:
                    if lang == 'en_US':
                        mess.append('Purchase Invoice')
                    else:
                        mess.append('Chứng từ mua hàng nhập kho')
                ### Chứng từ nhập kho - Stock In Inward
                if rec.is_misa_stock_in:
                    if lang == 'en_US':
                        mess.append('Stock Inward')
                    else:
                        mess.append('Chứng từ nhập kho')
                ### Chứng từ nhập kho - Trả hàng
                if rec.is_misa_return:
                    if lang == 'en_US':
                        mess.append('Stock Return')
                    else:
                        mess.append('Trả hàng')
                if rec.is_misa_stock_out:
                    if lang == 'en_US':
                        mess.append('Stock Outward')
                    else:
                        mess.append('Chứng từ xuất kho')
                if rec.is_misa_stock_internal:
                    if lang == 'en_US':
                        mess.append("Internal Transfer")
                    else:
                        mess.append('Chuyển kho nội bộ')
                if rec.is_misa_stock_other_in:
                    mess.append('Chứng từ nhập kho khác' if lang != 'en_US' else 'Other Stock Inward')
            if len(mess) > 0:
                mess = ' - '.join(mess)
                rec.noti_status_misa = '(' + mess + ')'
            else:
                rec.noti_status_misa = ''

    def sync_misa_stock_picking(self):
        """
        Mua hàng nhập kho:
            1.Chứng từ mua hàng nhập kho (Có hóa đơn- sẽ hiển thị thông tin về thuế)
            2.Phiếu nhập kho (Chứng từ mua hàng không có hóa đơn và ko có thông tin về thuế)

        Chứng từ nhập kho
            1. Thành phẩm sản xuất
            2. Hàng bán bị trả lại
            3. Khác (NVL thừa, HH thuê gia công)
        Xuất kho
            1. Bán hàng -- Sử dụng
            2. Sản xuất
            3. Xuất hàng cho chi nhánh khác
            3. Khác(Xuất sử dụng, góp vốn,...)

        """
        lang = self.env.lang or 'en_US'
        # Kiểm tra không đồng bộ sản phẩm chưa có trên Misa thì báo lỗi
        config = self.env['res.config.settings'].sudo()

        # Giới hạn số lượng đơn đồng bộ
        if self and len(self) > 100:
            raise UserError('Số lượng phiếu kho đồng bộ một lần không được vượt quá 100 đơn.')

        p_non = config.check_product_non_sync_misa(data=self.move_ids_without_package.mapped('product_id'))
        if p_non:
            product_names = '\n-'.join(p.display_name for p in p_non)
            raise UserError(
                f"Vui lòng đồng bộ sản phẩm trước khi đồng bộ đơn điều chuyển. "
                f"Sản phẩm chưa được đồng bộ với Misa:\n- {product_names}"
            )
        picking_type_id = self.mapped('picking_type_id')
        if picking_type_id and len(picking_type_id.ids) > 1:
            mess  = ', '.join(picking_type_id.mapped('name'))
            raise UserError(
                f'Không thể đồng bộ các phiếu kho khác loại.'
                f'Vui lòng chỉ chọn các phiếu cùng một loại hoạt động kho.\n'
                f'Các loại hoạt động kho đang được chọn: {mess}'
            )
        picking_non_sync = self.filtered(lambda p: p.state != 'done')
        if picking_non_sync:
            mess = ', '.join(picking_non_sync.mapped('name'))
            raise UserError(
                f'Chỉ đồng bộ được các phiếu kho ở trạng thái Hoàn thành.\n'
                f'Vui lòng hoàn thành các phiếu kho sau trước khi đồng bộ:\n{mess}\n'
            )

        # 1.Chứng từ mua hàng nhập kho
        record = self[0]
        if record.picking_type_code in ['incoming']:
            # Chứng từ mua hàng kèm hóa đơn (Hiện thị thông tin hoàn chỉnh kèm thuế)
            # Hàng bán trả lại  (Tạo DO nhập kho)
            if record.return_id or record.picking_type_id.is_misa_return:
                self.is_misa_return = True
                self.sync_misa_stock_picking_return(voucher_type=12)
            elif record.purchase_id:
                for rec in self:
                    if rec.purchase_id.misa_status != 'synced':
                        if lang == 'en_US':
                            raise UserError(rec.origin + ' needs to be synchronized before synchronizing the purchase invoice')
                        else:
                            raise UserError('Đơn mua hàng ' + rec.origin + ' cần đồng bộ trước khi đồng bộ chứng từ mua hàng (sản phẩm nhập kho)')
                self.is_misa_pu_invoice = True
                self.sync_misa_pu_invoice(voucher_type=18)
            # Phiếu nhập kho (không kèm hóa đơn)
            else:
                if record.partner_id and record.location_dest_id:
                    self.is_misa_stock_in = True
                    self.sync_misa_stock_picking_in(voucher_type=7)
        elif record.picking_type_code in ['outgoing']:
            # Hàng mua trả lại (Tạo DO xuất bán)
            if record.return_id or record.picking_type_id.is_misa_return:
                self.is_misa_return = True
                self.sync_misa_stock_picking_return(voucher_type=16)
            else:
                self.is_misa_stock_out = True
                self.sync_misa_stock_picking_out(voucher_type=8)

        elif record.picking_type_code in ['internal']:
            self.is_misa_stock_internal = True
            self.sync_misa_stock_picking_internal(voucher_type=9)
        elif record.picking_type_code in ['incoming_other']:
            self.is_misa_stock_other_in = True
            self.sync_misa_stock_picking_other_in(voucher_type=7)
        elif record.picking_type_code in ['outgoing_other']:
            self.is_misa_stock_other_out = True
            self.sync_misa_stock_picking_other_out(voucher_type=8)
        else:
            if lang == 'en_US':
                raise UserError('Not enough information to synchronize with Misa')
            else:
                raise UserError('Không đủ thông tin để đồng bộ với Misa')

    def sync_misa_stock_picking_in(self, voucher_type, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            error_miss = []
            lang = self.env.lang or 'en_US'
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": []
            }
            for rec in self:
                refdate = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                posted_date = config.get_datetime_format(rec.date_done, TIMEZONE_VN)
                # Đồng bộ kho Misa
                if rec.location_dest_id and not rec.location_dest_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + rec.location_dest_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + rec.location_dest_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')
                currency_id = 'VND'
    
                # thiếu thông tin sản phẩm
                if not rec.move_ids_without_package:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')
                journal_memo = ''
                if rec.note:
                    soup = BeautifulSoup(rec.note, 'html.parser')
                    plain_text = soup.get_text()
                    journal_memo = plain_text
                org_reftype_name = "Chứng từ  " + rec.name

                # Lấy theo khách hàng mặc định nếu khách hàng hiện tại k có code
                if rec.partner_id.customer_code:
                    account_object_code = rec.partner_id.customer_code
                elif rec.picking_type_id.default_customer:
                    account_object_code = rec.picking_type_id.default_customer.customer_code
                else:
                    account_object_code = ''

                if rec.sale_id and rec.sale_id.pancake_order_id:
                    account_object_code = rec.sale_id.pancake_order_id
                account_object_name =  rec.partner_id.name if rec.partner_id else ''
    
                voucher = {
                    "voucher_type": voucher_type,
                    "org_refid": rec.misa_id,
                    "org_refno": rec.origin or rec.name,
                    "org_reftype": rec.get_reftype_misa_stock(),
                    "org_reftype_name": org_reftype_name,

                    "currency_id": currency_id,

                    "refdate": refdate,
                    "refno": rec.name,

                    "posted_date": posted_date,

                    "account_object_code": account_object_code,
                    "account_object_name": account_object_name,
                    "account_object_address": config.get_address(rec.partner_id),

                    "account_object_tax_code": rec.partner_id.vat if rec.partner_id.vat else '',

                    "receive_address": config.get_address(rec.partner_id),

                    'discount_type': 0,

                    "journal_memo": journal_memo,

                    "reftype": rec.get_reftype_misa_stock(),
                    "due_day": 0,
                    "branch_id": "",
                    "status": rec.get_status_misa(),
                    "detail": []

                }
    
                # Thông tin chi tiết sản phẩm
                if rec.move_ids_without_package:
                    main_convert_rate = 1
                    exchange_rate = 1
                    sort_order = 1
                    for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                        line.sudo()._compute_stock_misa_internal()
                        if line.product_id:
                            # Diễn giải
                            is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm
    
                            unit_name = line.product_uom.name if line.product_uom.name else ""
    
                            if not line.product_id.default_code:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                                else:
                                    error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                                continue

                            # === LẤY KHO NHẬP TỪ PHIẾU ===
                            stock_code = stock_name = ''
                            if rec.location_dest_id and rec.location_dest_id.location_misa_id:
                                stock_code = rec.location_dest_id.location_misa_id.code
                                stock_name = rec.location_dest_id.location_misa_id.name
                            else:
                                error_miss.append(f'Chưa liên kết kho nhập "{rec.location_dest_id.name}" với MISA')
    
                            debit_account = line.misa_debit_account.code if line.misa_debit_account else False
                            credit_account = line.misa_credit_account.code if line.misa_credit_account else False
                            # Thiếu dữ liệu không cho đồng bộ
                            if not debit_account or not credit_account:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu thông tin Tài Khoản để đồng bộ Misa')
                                else:
                                    error_miss.append('Insufficient Account Information to Synchronize Misa')
                                continue
                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,
    
                                "account_object_code": account_object_code,
                                "account_object_name": account_object_name,
    
                                "quantity": line.quantity,
                                "main_quantity": line.quantity,
    
                                "unit_name": unit_name,
                                "main_unit_name": unit_name,
                                "unit_price": line.purchase_line_id.price_unit if line.purchase_line_id else 0.0,
                                "sort_order": sort_order,
                                "is_promotion": False,
    
                                "debit_account": debit_account,
                                "credit_account": credit_account,
    
                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,
    
                                "status": rec.get_status_misa(),
    
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                            }
                            lot_no, expiry_date = config.get_info_lot_product(data=line)  # todo check xem lot lấy stock.move hay sotck.move.line
                            if lot_no:
                                data_sale_line['lot_no'] = lot_no
                            if expiry_date:
                                data_sale_line['expiry_date'] = expiry_date
    
                            sort_order += 1
                            if voucher:
                                voucher["detail"].append(data_sale_line)

                # add to body
                body['voucher'].append(voucher)
            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            records = self.sudo()
            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    records.sudo().misa_status = 'synced'
                else:
                    # Token hết hạn
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        records.sync_misa_stock_picking_in(reset_token=True)
                    else:
                        records.sudo().misa_status = 'sync_failed'
            else:
                records.sudo().misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']

            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            func = ','.join(self.mapped('name'))
            IrLogging.sudo().create({'name': 'sync_misa_stock_picking_in',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self[0]._name),
                                     'func': func,
                                     'line': 1})


    def sync_misa_stock_picking_return(self, voucher_type, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        branch_id = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.branch_id', '')
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            error_miss = []
            lang = self.env.lang or 'en_US'
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": [],
            }
            for rec in self:
                refdate = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                posted_date = config.get_datetime_format(rec.date_done, TIMEZONE_VN)
    
                # Đồng bộ kho Misa
                warehouse = None
                if rec.picking_type_code == 'incoming':
                    warehouse = rec.location_dest_id
                elif rec.picking_type_code == 'outgoing':
                    warehouse = rec.location_id
    
                if warehouse and not warehouse.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append(f'Chưa liên kết thông tin kho "{warehouse.name}" với kho có trên Misa')
                    else:
                        error_miss.append(
                            f'Inventory information for the "{warehouse.name}" warehouse has not been synchronized with the warehouse in Misa.')
                # employee_code, employee_name = config.get_employee_name(data=rec.user_id)
    
                currency_id = 'VND'
    
                # thiếu thông tin sản phẩm
                if not rec.move_ids_without_package:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')
                parts = ["Trả lại hàng bán của: "]
    
                # Mã đơn
                if rec.sale_id and rec.sale_id.name:
                    parts.append(rec.sale_id.name)
    
                # Kênh bán hàng
                if rec.sale_id and rec.sale_id.pancake_source_id:
                    parts.append(rec.sale_id.pancake_source_id.name)
                journal_memo = " - ".join(parts)
                org_reftype_name = "Chứng từ  " + rec.name
                if rec.return_id:
                    org_reftype_name = "Hàng trả lại" + rec.name

                # Lấy theo khách hàng mặc định nếu khách hàng hiện tại k có code
                if rec.partner_id.customer_code:
                    account_object_code = rec.partner_id.customer_code
                elif rec.picking_type_id.default_customer:
                    account_object_code = rec.picking_type_id.default_customer.customer_code
                else:
                    account_object_code = ''

                if rec.sale_id and rec.sale_id.pancake_order_id:
                    account_object_code = rec.sale_id.pancake_order_id
                account_object_name =  rec.partner_id.name if rec.partner_id else ''
                if rec.sale_id and rec.sale_id.pancake_source_id and rec.sale_id.pancake_source_id.default_customer:
                    account_object_code = rec.sale_id.pancake_source_id.default_customer.customer_code or ''
                    account_object_name = rec.sale_id.pancake_source_id.default_customer.name or ''

                voucher_data = {
                    # ===== THÔNG TIN MASTER =====
                    "voucher_type": voucher_type,  # Trả lại hàng bán 12
    
                    "org_refid": rec.misa_id,
                    "org_refno": rec.origin or rec.name,
                    "org_reftype": rec.get_reftype_misa_stock(),
                    "org_reftype_name": org_reftype_name,
    
                    "currency_id": currency_id,
    
                    "refdate": refdate,
                    "refno": rec.name,
    
                    "posted_date": posted_date,
                    "exchange_rate": 1,
                    "inv_date": fields.Date.to_string(rec.create_date.date()),
                    "inv_no": rec.name,
                    "inv_series": rec.name,

                    "account_object_code": account_object_code,
                    "account_object_name": account_object_name,
                    "account_object_address": config.get_address(rec.partner_id),
                    "account_object_tax_code": rec.partner_id.vat or "",
    
                    "receive_address": config.get_address(rec.partner_id),

                    "discount_type": 0,
    
                    "journal_memo": journal_memo,
    
                    "due_day": 0,
                    "branch_id": branch_id,
                    "status": rec.get_status_misa(),
    
                    # ===== CHI TIẾT HÀNG HÓA =====
                    "detail": [],
                }
                if rec.return_id:
                    voucher_data.update({
                        "reftype": 3540,  # Hàng bán bị trả lại - Giảm trừ công nợ
    
                        "is_return_with_inward": True,
    
                        # ===== CHI TIẾT HÀNG HÓA =====
                        "detail": [],
    
                        # ---- phiếp nhập kho ----
                        "in_inward": {
                            "reftype": 2013,
                            "reftype_name": "Nhập kho từ hàng bán trả lại",
    
                            "refdate": refdate,
                            "posted_date": posted_date,
    
                            "account_object_code": account_object_code,
                            "account_object_name": account_object_name,
                            "account_object_address": config.get_address(rec.partner_id),
    
                            "branch_id": branch_id,
                            "journal_memo": journal_memo,
    
                            "is_return_with_inward": True,
                        },
    
                        # ------ hóa đơn ------
                        "pu_invoice": {
                            "reftype": 3403,  # Hóa đơn hàng bán bị trả lại
                            "inv_date": fields.Date.to_string(rec.create_date.date()),
                            "refdate": config.get_datetime_format(rec.create_date, TIMEZONE_VN),
                            "inv_no": rec.name,
                            "inv_series": rec.name,
                            "branch_id": branch_id,
                            "posted_date": config.get_datetime_format(rec.create_date, TIMEZONE_VN),
                            "inv_template_no": '2',

                        },
                    })
    
    
                # Thông tin chi tiết sản phẩm
                if rec.move_ids_without_package:
                    main_convert_rate = 1
                    exchange_rate = 1
                    sort_order = 1
                    for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                        line.sudo()._compute_stock_misa_internal()
                        if line.product_id:
                            # Diễn giải
                            is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm
    
                            if not line.product_id.default_code:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                                else:
                                    error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                                continue
    
                            stock_id = stock_code = stock_name = ''
                            if rec.picking_type_code in ['incoming']:
                                if line.stock_misa_to:
                                    stock_id, stock_code, stock_name = config.get_stock_misa(stock=line.stock_misa_to)
                            if rec.picking_type_code in ['outgoing']:
                                if line.stock_misa_from:
                                    stock_id, stock_code, stock_name = config.get_stock_misa(stock=line.stock_misa_from)
    
                            debit_account = line.misa_debit_account.code if line.misa_debit_account else False
                            credit_account = line.misa_credit_account.code if line.misa_credit_account else False
                            stock_account = line.misa_account_inventory.code if line.misa_account_inventory else False
                            cost_account = line.misa_cost_account.code if line.misa_cost_account else False
                            # Ưu tiên lấy theo đơn vị đồng bộ từ Misa
                            unit_name = line.product_uom.name if line.product_uom.name else ""
    
                            # Thiếu dữ liệu không cho đồng bộ
                            if not debit_account or not credit_account:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu thông tin Tài Khoản để đồng bộ Misa')
                                else:
                                    error_miss.append('Insufficient Account Information to Synchronize Misa')
                                continue
                            cost_unit_price = line.product_id.standard_price
                            quantity = line.quantity
                            if rec.return_id:
                                sale_line = False
    
                                if line.origin_returned_move_id and line.origin_returned_move_id.sale_line_id:
                                    sale_line = line.origin_returned_move_id.sale_line_id
    
                                elif line.sale_line_id:
                                    sale_line = line.sale_line_id
    
                                if sale_line:
                                    cost_price = sale_line.price_unit
                                else:
                                    cost_price = line.product_id.standard_price
                            else:
                                # KHÔNG PHẢI TRẢ HÀNG
                                cost_price = line.product_id.standard_price
                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,
    
                                "quantity": line.quantity,
                                "main_quantity": line.quantity,
                                "main_quantity": line.quantity,
                                "main_unit_price": line.price_unit,

                                "unit_name": unit_name,
                                "main_unit_name": unit_name,
    
                                "sort_order": sort_order,
                                "is_promotion": False,
    
                                "debit_account": debit_account,
                                "credit_account": credit_account,
    
                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,
    
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                # ----- Tab giá vốn :Đơn giá vốn và tiền vốn ------
                                "cost_unit_price_finance" : cost_unit_price,
                                "cost_amount_finance" : cost_unit_price * quantity,
                                "cost_account": cost_account,
                                "stock_account": stock_account,
                                # ----- Tab hàng tiền :Đơn giá và thành tiền ------
                                'unit_price': cost_price, # Đơn giá
                                'amount_oc' : cost_price * quantity, # Thành tiền
                                'amount' : cost_price * quantity, # Thành tiền
                                "inventory_item_type": 0,
                                "inventory_resale_type_id": 0,
                                "not_in_vat_declaration": False,
                                "purchase_purpose_id": "ed4bd91d-83ac-4a26-b4c1-4bce85faecb8",
                                "vat_rate": 8,
                                "vat_amount": cost_price * quantity * 8 / 100,
                                "vat_amount_oc": cost_price * quantity * 8 / 100
                            }
                            lot_no, expiry_date = config.get_info_lot_product(data=line)  # todo check xem lot lấy stock.move hay sotck.move.line
                            if lot_no:
                                data_sale_line['lot_no'] = lot_no
                            if expiry_date:
                                data_sale_line['expiry_date'] = expiry_date
    
                            sort_order += 1
                            if voucher_data:
                                voucher_data["detail"].append(data_sale_line)

                # add to body
                body['voucher'].append(voucher_data)

            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            records = self.sudo()
            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    records.sudo().misa_status = 'synced'
                else:
                    # Token hết hạn
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        records.sync_misa_stock_picking_in(reset_token=True)
                    else:
                        records.sudo().misa_status = 'sync_failed'
            else:
                records.sudo().misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']

            func = ','.join(self.mapped('name'))
            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_stock_picking_return',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self[0]._name),
                                     'func': func,
                                     'line': 1})

    def sync_misa_stock_picking_out(self, voucher_type, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            error_miss = []
            lang = self.env.lang or 'en_US'
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": []
            }
            for rec in self:
                # Đồng bộ kho Misa
                if rec.location_id and not rec.location_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + rec.location_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + rec.location_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')
                # thiếu thông tin sản phẩm
                if not rec.move_ids_without_package:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')

                currency_id = 'VND'

                org_reftype_name = rec.origin if rec.origin else "Chứng từ xuất kho " + rec.name
                org_refno = rec.origin if rec.origin else rec.name

                refdate = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                posted_date = config.get_datetime_format(rec.date_done, TIMEZONE_VN)

                # Địa chỉ giao hàng
                shipping_address = rec.address_partner_detail

                # Lấy thông tin mặc định từ partner
                # Lấy theo khách hàng mặc định nếu khách hàng hiện tại k có code
                if rec.partner_id.customer_code:
                    account_object_code = rec.partner_id.customer_code
                elif rec.partner_id.parent_id and rec.partner_id.parent_id.customer_code:
                    account_object_code = rec.partner_id.parent_id.customer_code
                elif rec.picking_type_id.default_customer:
                    account_object_code = rec.picking_type_id.default_customer.customer_code
                else:
                    account_object_code = ''

                account_object_name = rec.partner_id.name or '' if rec.partner_id else ''

                if rec.sale_id and rec.sale_id.pancake_source_id and rec.sale_id.pancake_source_id.default_customer:
                    account_object_code = rec.sale_id.pancake_source_id.default_customer.customer_code or ''
                    account_object_name = rec.sale_id.pancake_source_id.default_customer.name or ''
    
                # Ghi đè nếu có thông tin từ sale
                journal_memo = account_object_name
                sale = rec.sale_id
                if sale:
                    # Đơn Pancake
                    if sale.pancake_order_id:
                        journal_memo += ' - ' + sale.pancake_source_id.name
                        # Mã KH là mã đơn hàng trên Pancake
                        # Tên KH lấy theo pancake nếu có
                        account_object_code = sale.pancake_order_id
                        account_object_name = sale.partner_id.name
                        if ('*' in account_object_name
                                and sale.shipping_full_name
                                and '*' not in sale.shipping_full_name):
                            account_object_name = sale.shipping_full_name
                    # Đơn khách sỉ
                    if sale.name_wholesaler:
                        journal_memo += ' - ' + sale.name_wholesaler

                if not account_object_code:
                    raise UserError(_("Customer code is not configured."))

    
                voucher =  {
                    "voucher_type": voucher_type,
    
                    "org_refid": rec.misa_id,
                    "org_refno": org_refno,
                    "org_reftype": rec.get_reftype_misa_stock(),
                    "org_reftype_name": org_reftype_name,
    
                    "currency_id": currency_id,
    
                    "refdate": refdate,
                    "refno": rec.name,
    
                    "posted_date": posted_date,
                    "account_object_code": account_object_code,
                    "account_object_name": account_object_name,
                    "account_object_address": shipping_address,
                    "shipping_address": shipping_address,
    
    
                    "account_object_tax_code": rec.partner_id.vat if rec.partner_id.vat else '',
    
                    "receive_address": config.get_address(rec.partner_id),
    
                    'discount_type': 0,
    
                    "journal_memo": journal_memo,
    
                    "reftype": rec.get_reftype_misa_stock(),
                    "due_day": 0,
                    "branch_id": "",
                    "status": rec.get_status_misa(),
                    "detail": []
                }
    
                # Thông tin chi tiết sản phẩm
                if rec.move_ids_without_package:
                    main_convert_rate = 1
                    exchange_rate = 1
                    sort_order = 1
                    for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                        line.sudo()._compute_stock_misa_internal()
                        if line.product_id:
                            stock_id = stock_code = stock_name = ''
                            if line.stock_misa_from:
                                stock_id, stock_code, stock_name = config.get_stock_misa(stock=line.stock_misa_from)
                            # Diễn giải
                            is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm
                            unit_name = line.product_uom.name if line.product_uom.name else ""
    
                            if not line.product_id.default_code:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                                else:
                                    error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                                continue
    
                            debit_account = line.misa_debit_account.code if line.misa_debit_account else None
                            credit_account = line.misa_credit_account.code if line.misa_credit_account else None
                            # Thiếu dữ liệu không cho đồng bộ
                            if not debit_account or not credit_account:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu thông tin Tài Khoản để đồng bộ Misa')
                                else:
                                    error_miss.append('Insufficient Account Information to Synchronize Misa')
                                continue
                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,
    
                                "account_object_code": account_object_code,
                                "account_object_name": account_object_name,
    
                                "quantity": line.quantity,
                                "main_quantity": line.quantity,
    
                                "unit_name": unit_name,
                                "main_unit_name": unit_name,
    
                                "sort_order": sort_order,
                                "is_promotion": False,
    
                                "debit_account": debit_account,
                                "credit_account": credit_account,
    
                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,
    
                                "status": rec.get_status_misa(),
    
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                            }
                            lot_no, expiry_date = config.get_info_lot_product(data=line)  # todo check xem lot lấy stock.move hay sotck.move.line
                            if lot_no:
                                data_sale_line['lot_no'] = lot_no
                            if expiry_date:
                                data_sale_line['expiry_date'] = expiry_date
    
                            sort_order += 1
                            if voucher:
                                voucher["detail"].append(data_sale_line)

                # add to body
                body['voucher'].append(voucher)
            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            records = self.sudo()
            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    records.misa_status = 'synced'
                else:
                    # Token hết hạn
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        records.sync_misa_stock_picking_out(reset_token=True)
                    else:
                        records.misa_status = 'sync_failed'
            else:
                records.misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']

            func = ','.join(self.mapped('name'))
            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_stock_picking_out',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self[0]._name),
                                     'func': func,
                                     'line': 1})

    def sync_misa_pu_invoice(self, voucher_type, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

            for rec in self:
                refdate = config.get_datetime_format(rec.purchase_id.date_approve, TIMEZONE_VN)
                posted_date = config.get_datetime_format(rec.date_done, TIMEZONE_VN)
                created_date = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                write_date = config.get_datetime_format(rec.write_date, TIMEZONE_VN)

                connect_url = api_url + '/apir/sync/actopen/save'
                headers = {
                    'X-MISA-AccessToken': token,
                    'Content-Type': 'application/json'
                }

                error_miss = []
                lang = self.env.lang or 'en_US'
                # # Kiểm tra mã khách hàng
                # if self.partner_id and not self.partner_id.customer_code:
                #     if lang == 'vi_VN':
                #         error_miss.append('Thiếu thông tin mã khách hàng: \"' + self.partner_id.name + '\"')
                #     else:
                #         error_miss.append('Missing customer code information: \"' + self.partner_id.name + '\"')

                # Đồng bộ kho Misa
                if rec.location_dest_id and not rec.location_dest_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + rec.location_dest_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + rec.partner_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')

                include_invoice = int(rec.purchase_id.include_invoice_misa) if rec.purchase_id.include_invoice_misa else 0

                employee_code, employee_name = config.get_employee_name(data=rec.user_id)

                currency_id = rec.purchase_id.currency_id.name if rec.purchase_id.currency_id else 'VND'

                due_day = rec.purchase_id.number_of_days_owed if rec.purchase_id else 0

                due_time = rec.purchase_id.number_of_days_owed
                due_date = ""
                if due_time > 0 and refdate:
                    new_date = rec.purchase_id.date_approve + timedelta(days=due_time)
                    due_date = config.get_datetime_format(new_date, TIMEZONE_VN)
                # thiếu thông tin sản phẩm
                if not rec.move_ids_without_package:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')
                account_object_code = rec.partner_id.customer_code if rec.partner_id.customer_code else ''
                if rec.sale_id and rec.sale_id.pancake_order_id:
                    account_object_code = rec.sale_id.pancake_order_id
                account_object_name =  rec.partner_id.name if rec.partner_id else ''
                body = {
                    "app_id": app_id,
                    "org_company_code": org_company_code,
                    "voucher": [
                        {
                            "voucher_type": voucher_type,

                            "include_invoice": include_invoice,

                            "org_refid": rec.misa_id,
                            "org_refno": rec.purchase_id.name,
                            "org_reftype": 302,
                            "org_reftype_name": "Mua hàng nhập kho " + rec.purchase_id.name,

                            "currency_id": currency_id,

                            "refdate": refdate,
                            "refno": rec.purchase_id.name + '-' + rec.name,

                            "posted_date": posted_date,

                            "created_date": created_date,
                            "created_by": rec.create_uid.name if rec.create_uid else '',
                            "modified_date": write_date,
                            "modified_by": rec.write_uid.name if rec.write_uid else '',

                            "account_object_code": account_object_code,
                            "account_object_name": account_object_name,
                            "account_object_address": config.get_address(rec.partner_id),
                            "account_object_tax_code": rec.partner_id.vat if rec.partner_id.vat else '',

                            "receive_address": config.get_address(rec.partner_id),

                            # "employee_id": config.sudo().encode_uuid(str_id='res_user_' + str(rec.user_id.id)),
                            "employee_code": employee_code,
                            "employee_name": employee_name,

                            'discount_type': 0,

                            "exchange_rate": rec.purchase_id.exchange_rate,

                            "journal_memo": "",

                            "reftype": 302,
                            "due_day": due_day,
                            "branch_id": "",
                            "status": rec.get_status_misa(),

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
                if rec.move_ids_without_package:
                    main_convert_rate = rec.purchase_id.convert
                    convert = rec.purchase_id.convert
                    exchange_rate = rec.purchase_id.exchange_rate
                    sort_order = 1
                    for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                        line.sudo()._compute_stock_misa_internal()
                        if line.product_id:
                            # Discount theo sản phẩm
                            discount_type, discount_rate, discount_amount, discount_amount_oc, vat_rate, vat_amount, vat_amount_oc = rec.env['purchase.order'].sudo().get_discount_vat_misa(data=line.purchase_line_id, exchange_rate=exchange_rate, convert=convert)
                            total_discount_amount += discount_amount
                            total_discount_amount_oc += discount_amount_oc
                            total_vat_amount += vat_amount
                            total_vat_amount_oc += vat_amount_oc

                            # Tổng tiền
                            amount, amount_oc = rec.env['purchase.order'].sudo().get_amount_misa(data=line.purchase_line_id, exchange_rate=exchange_rate, convert=convert)
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

                            stock_id = stock_code = stock_name = ''
                            if line.stock_misa_to:
                                stock_id, stock_code, stock_name = config.get_stock_misa(stock=line.stock_misa_to)

                            debit_account = line.misa_debit_account.code if line.misa_debit_account else None
                            credit_account = line.misa_credit_account.code if line.misa_credit_account else None
                            misa_account_inventory = line.misa_account_inventory.code if line.misa_account_inventory else None
                            # Thiếu dữ liệu không cho đồng bộ
                            if not debit_account or not credit_account:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu thông tin Tài Khoản để đồng bộ Misa')
                                else:
                                    error_miss.append('Insufficient Account Information to Synchronize Misa')
                                continue
                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,

                                "account_object_code": account_object_code,
                                "account_object_name": account_object_name,

                                "quantity": line.quantity,
                                "main_quantity": line.quantity,

                                "unit_name": line.product_uom.name if line.product_uom else '',
                                "unit_price": line.purchase_line_id.price_unit if line.purchase_line_id else 0.0,

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

                                "stock_code": stock_code,
                                "stock_name": stock_name,

                                "debit_account": debit_account,
                                "credit_account": credit_account,

                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,

                                "status": rec.get_status_misa(),

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
                                for line in rec.order_line:
                                    base_price = line._get_pricelist_price_before_discount()
                                    total_base_price += base_price
                                if total_base_price > 0:
                                    detail["discount_rate_voucher"] = round(total_discount_amount_oc / total_base_price * 100, 2)

                            # Điều khoản thanh toán và Số ngày được nợ
                            payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(data=rec.purchase_id.payment_term_id)
                            if payment_term_id:
                                detail["payment_term_id"] = payment_term_id
                                detail["payment_term_code"] = payment_term_code
                                detail["payment_term_name"] = payment_term_name
                            else:
                                if rec.purchase_id.payment_term_id:
                                    if lang == 'vi_VN':
                                        error_miss.append('Thiếu thông tin điều khoản thanh toán Misa: \"' + payment_term_name + '\"')
                                    else:
                                        error_miss.append('Missing Misa payment term code information: \"' + payment_term_name + '\"')
                            # Diễn giải
                            if rec.note:
                                soup = BeautifulSoup(rec.note, 'html.parser')
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
                        rec.sudo().misa_status = 'synced'
                    else:
                        # Token hết hạn
                        if data['ErrorCode'] == 'ExpiredToken':
                            print('Expired Token')
                            rec.sync_misa_pu_invoice(reset_token=True)
                        else:
                            rec.sudo().misa_status = 'sync_failed'
                else:
                    rec.sudo().misa_status = 'sync_failed'

                IrLogging = self.env['ir.logging']

                func = ','.join(rec.mapped('name'))
                message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
                IrLogging.sudo().create({'name': 'sync_misa_pu_invoice',
                                         'type': 'server',
                                         'message': message,
                                         'path': str(rec[0]._name),
                                         'func': rec.name,
                                         'line': 1})

    def sync_misa_stock_picking_internal(self, voucher_type=False, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

            for rec in self:
                refdate = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                posted_date = config.get_datetime_format(rec.date_done, TIMEZONE_VN)

                created_date = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
                write_date = config.get_datetime_format(rec.write_date, TIMEZONE_VN)

                connect_url = api_url + '/apir/sync/actopen/save'
                headers = {
                    'X-MISA-AccessToken': token,
                    'Content-Type': 'application/json'
                }
                error_miss = []
                lang = self.env.lang or 'en_US'
                # Kiểm tra mã khách hàng
                # if self.partner_id and not self.partner_id.customer_code:
                #     if lang == 'vi_VN':
                #         error_miss.append('Thiếu thông tin mã khách hàng: \"' + self.partner_id.name + '\"')
                #     else:
                #         error_miss.append('Missing customer code information: \"' + self.partner_id.name + '\"')

                # Đồng bộ kho Misa
                if rec.location_dest_id and not rec.location_dest_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + rec.location_dest_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + rec.location_dest_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')

                if rec.location_id and not rec.location_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + rec.location_dest_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + rec.location_dest_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')

                employee_code, employee_name = config.get_employee_name(data=rec.user_id)
                transporter_code, transporter_name = config.get_employee_name_detail(employee=rec.em_transporter)

                currency_id = 'VND'

                # thiếu thông tin sản phẩm
                if not rec.move_ids_without_package:
                    if lang == 'vi_VN':
                        error_miss.append('Thiếu thông tin chi tiết sản phẩm')
                    else:
                        error_miss.append('Missing products information')

                journal_memo = f"Phiếu điều chuyển nội bộ từ kho {rec.location_id.name or ''} đến {rec.location_dest_id.name or ''}"
                if rec.origin:
                    journal_memo += f" {rec.origin}"
                account_object_code = rec.partner_id.customer_code if rec.partner_id.customer_code else ''
                if rec.sale_id and rec.sale_id.pancake_order_id:
                    account_object_code = rec.sale_id.pancake_order_id

                account_object_name =  rec.partner_id.name if rec.partner_id else ''
                account_object_address = config.get_address(rec.partner_id)

                body = {
                    "app_id": app_id,
                    "org_company_code": org_company_code,
                    "voucher": [
                        {
                            "voucher_type": voucher_type,

                            "org_refid": rec.misa_id,
                            "org_refno": rec.origin or rec.name,
                            "org_reftype": rec.get_reftype_misa_stock(),
                            "org_reftype_name": "Xuất chuyển kho nội bộ " + rec.name,

                            "currency_id": currency_id,

                            "refdate": refdate,
                            "refno": rec.name,

                            "posted_date": posted_date,

                            "created_date": created_date,
                            "created_by": rec.create_uid.name if rec.create_uid else '',
                            "modified_date": write_date,
                            "modified_by": rec.write_uid.name if rec.write_uid else '',

                            "account_object_code": account_object_code,
                            "account_object_name": account_object_name,
                            "account_object_address": account_object_address,
                            "account_object_tax_code": rec.partner_id.vat if rec.partner_id.vat else '',

                            "receive_address": config.get_address(rec.partner_id),

                            "employee_code": employee_code,
                            "employee_name": employee_name,

                            "transporter_code": transporter_code,
                            "transporter_name": transporter_name,

                            'discount_type': 0,

                            "journal_memo": journal_memo,

                            "reftype": rec.get_reftype_misa_stock(),
                            "due_day": 0,
                            "branch_id": "",
                            "status": rec.get_status_misa(),

                            "detail": []
                        }],
                }

                # Thông tin chi tiết sản phẩm
                if rec.move_ids_without_package:
                    main_convert_rate = 1
                    exchange_rate = 1
                    sort_order = 1
                    for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                        line.sudo()._compute_stock_misa_internal()
                        if line.product_id:
                            # Diễn giải
                            is_description = False  # Nếu False thì phải truyền inventory_item_id  sản phẩm

                            if not line.product_id.default_code:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu mã sản phẩm \"' + line.product_id.name + '\"')
                                else:
                                    error_miss.append('Missing customer code information  \"' + line.product_id.name + '\"')
                                continue

                            from_stock_id = from_stock_code = from_stock_name = ''
                            to_stock_id = to_stock_code = to_stock_name = ''
                            if line.stock_misa_from:
                                from_stock_id, from_stock_code, from_stock_name = config.get_stock_misa(stock=line.stock_misa_from)
                            if line.stock_misa_to:
                                to_stock_id, to_stock_code, to_stock_name = config.get_stock_misa(stock=line.stock_misa_to)

                            debit_account = line.misa_debit_account.code if line.misa_debit_account else False
                            credit_account = line.misa_credit_account.code if line.misa_credit_account else False
                            # Thiếu dữ liệu không cho đồng bộ
                            if not debit_account or not credit_account:
                                if lang == 'vi_VN':
                                    error_miss.append('Thiếu thông tin Tài Khoản để đồng bộ Misa')
                                else:
                                    error_miss.append('Insufficient Account Information to Synchronize Misa')
                                continue
                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code if line.product_id.default_code else '',
                                "inventory_item_name": line.product_id.name if line.product_id.name else '',
                                "description": line.product_id.name if line.product_id.name else '',
                                "is_description": is_description,

                                "account_object_code": account_object_code,
                                "account_object_name": account_object_name,

                                "quantity": line.quantity,
                                "main_quantity": line.quantity,

                                "unit_name": line.product_uom.name if line.product_uom else '',
                                "main_unit_name": line.product_uom.name if line.product_uom else '',

                                "sort_order": sort_order,
                                "is_promotion": False,

                                "inventory_resale_type_id": config.get_inventory_resale_type_id(data=False),  # Chưa biết là gì mặc định để 0

                                "debit_account": debit_account,
                                "credit_account": credit_account,

                                "exchange_rate_operator": "*",
                                "main_convert_rate": main_convert_rate,
                                "exchange_rate": exchange_rate,
                                "currency_id": currency_id,

                                "status": rec.get_status_misa(),

                                "from_stock_code": from_stock_code,
                                "from_stock_name": from_stock_name,

                                "to_stock_code": to_stock_code,
                                "to_stock_name": to_stock_name,
                            }
                            lot_no, expiry_date = config.get_info_lot_product(data=line)  # todo check xem lot lấy stock.move hay sotck.move.line
                            if lot_no:
                                data_sale_line['lot_no'] = lot_no
                            if expiry_date:
                                data_sale_line['expiry_date'] = expiry_date

                            sort_order += 1
                            if body["voucher"][0]:
                                detail = body["voucher"][0]
                                detail["detail"].append(data_sale_line)

                if len(error_miss):
                    mess = '\n'.join(error_miss)
                    raise UserError(mess)
                payload = json.dumps(body)
                response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

                if response.status_code == 200:
                    data = json.loads(response.text)
                    if data['Success']:
                        rec.sudo().misa_status = 'synced'
                    else:
                        # Token hết hạn
                        if data['ErrorCode'] == 'ExpiredToken':
                            print('Expired Token')
                            rec.sync_misa_stock_picking_internal(reset_token=True)
                        else:
                            rec.sudo().misa_status = 'sync_failed'
                else:
                    rec.sudo().misa_status = 'sync_failed'

                IrLogging = self.env['ir.logging']

                message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
                func = ','.join(rec.mapped('name'))
                IrLogging.sudo().create({'name': 'sync_misa_stock_picking_internal',
                                         'type': 'server',
                                         'message': message,
                                         'path': str(rec[0]._name),
                                         'func': func,
                                         'line': 1})

    def get_reftype_misa(self):
        """
        Bao gồm hóa đơn (mặc định chưa thanh toán)
            302: Mua hàng trong nước nhập kho chưa thanh toán
            312: Mua hàng trong nước không qua kho chưa thanh toán
            318: Mua hàng nhập khẩu nhập kho chưa thanh toán

        * Hàng nhập khẩu luôn lưu kho
        * Hàng trong nước có lưu kho hoặc không
        """
        reftype = 302
        if self.purchase_id:
            if self.purchase_id.purchase_order_type and self.purchase_id.purchase_order_type == 'foreign':
                reftype = 318

        return reftype

    def get_status_misa(self):
        """
        Tình trạng đơn hàng:   1: Chưa thực hiện;
                               2: Đang thực hiện;
                               3: Hoàn thành
                               4: Hủy bỏ
        """
        self.ensure_one()
        status = 3  # Mặc định gửi hoàn thành mới tạo chưng từ mua hàng
        # if self.state in ['done']:
        #     status = 3
        if self.state in ['cancel']:
            status = 4
        return status

    def get_reftype_misa_stock(self):
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


        Chứng từ nhập kho
                2010: Nhập kho thành phẩm sản xuất
                2011: Nhập kho thành phẩm lắp ráp
                2012: Nhập kho thành phẩm tháo dỡ
                2013: Nhập kho từ hàng bán trả lại
                2014: Nhập kho khác (Nhập kho)
                2015: Nhập kho từ kiểm kê
                2016: Nhập kho từ kiểm kê (Có điều chỉnh giá trị)
                2017: Nhập kho hàng nhận gia công

        Chứng từ xuất kho:
                2020: Xuất kho bán hàng
                2021: Xuất hàng cho chi nhánh khác
                2022: Xuất kho khác
                2023: Xuất kho sản xuất
                2024: Xuất kho lắp ráp
                2025: Xuất kho tháo dỡ
                2026: Xuất kho từ kiểm kê
                2027: Xuất kho từ kiểm kê (Có điều chỉnh giá trị)

        Chhuyển kho
                2030: Xuất kho kiêm vận chuyển nội bộ
                2031: Xuất kho gửi bán đại lý
                2032: Xuất chuyển kho nội bộ


        """
        reftype = 2014
        self.ensure_one()
        if self.picking_type_id:
            code = self.picking_type_id.code
            if code in ['incoming']:
                # Bán hàng trả lại (Tính DO nhâp từ hàng bán trả lại)
                if self.return_id or self.picking_type_id.is_misa_return:
                    reftype = 2013
                # Chứng từ mua hàng
                elif self.purchase_id:
                    reftype = 302
                    if self.purchase_id.is_buying_cost:
                        reftype = 330
            # nhập kho khác
            if code in ['incoming_other']:
                reftype = 2014
                # Bán hàng trả lại (Tính DO nhâp từ hàng bán trả lại)
                if self.return_id or self.picking_type_id.is_misa_return:
                    reftype = 2013
            # xuất kho
            if code in ['outgoing']:
                reftype = 2020
                # Mua hàng trả lại (Tạo DO xuất bán để trả hàng)
                if self.return_id or self.picking_type_id.is_misa_return:
                    reftype = 3030
            # xuất kho khác
            if code in ['outgoing_other']:
                reftype = 2022
                # Mua hàng trả lại (Tạo DO xuất bán để trả hàng)
                if self.return_id or self.picking_type_id.is_misa_return:
                    reftype = 3030
            # Chuyển nội bộ
            if code in ['internal']:
                reftype = 2032
        # print('reftype: ', reftype)
        return reftype

    # todo Đồng bộ hàng loạt
    def sync_misa_stock_picking_other_in(self, voucher_type=7, reset_token=False):
        """Đồng bộ Phiếu nhập kho khác → MISA (reftype=2014)"""
        # self.ensure_one()
        api_url, app_id, access_code, org_company_code, token = self.env[
            'res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if not (api_url and app_id and org_company_code and token):
            return

        config = self.env['res.config.settings'].sudo()
        TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

        for rec in self:
            refdate = config.get_datetime_format(rec.date_done or rec.create_date, TIMEZONE_VN)
            posted_date = config.get_datetime_format(rec.date_done or rec.create_date, TIMEZONE_VN)


            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {'X-MISA-AccessToken': token, 'Content-Type': 'application/json'}
            error_miss = []
            lang = self.env.lang or 'en_US'

            # === KIỂM TRA BẮT BUỘC ===
            if not rec.move_ids_without_package:
                error_miss.append('Thiếu thông tin chi tiết sản phẩm')

            # Kho nhập
            if rec.location_dest_id and not rec.location_dest_id.location_misa_id:
                error_miss.append(f'Chưa liên kết kho nhập "{rec.location_dest_id.name}" với MISA')

            # Đối tượng (nếu có)
            if rec.partner_id:
                # Tên + mã đối tượng
                account_object_name = rec.partner_id.name
            else:
                account_object_name = ''

            # Lấy theo khách hàng mặc định nếu khách hàng hiện tại k có code
            if rec.partner_id.customer_code:
                account_object_code = rec.partner_id.customer_code
            elif rec.picking_type_id.default_customer:
                account_object_code = rec.picking_type_id.default_customer.customer_code
            else:
                error_miss.append(f'Thiếu mã đối tượng (ref) cho "{rec.partner_id.name}"')

            # Ghi chú
            journal_memo = ''
            if rec.note:
                soup = BeautifulSoup(rec.note, 'html.parser')
                journal_memo = soup.get_text()

            #  THÊM: Điều khoản thanh toán và Số ngày nợ (nếu có PO liên quan)
            payment_term_id = payment_term_code = payment_term_name = ''
            due_day = 0
            if rec.purchase_id:
                payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(
                    data=rec.purchase_id.payment_term_id)
                due_day = rec.purchase_id.number_of_days_owed or 0
            else:
                # Nếu không có PO → để trống
                pass
            if rec.sale_id:
                account_object_code = rec.sale_id.pancake_order_id
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": [{
                    "voucher_type": voucher_type,
                    "org_refid": rec.misa_id,
                    "org_refno": rec.origin or rec.name,
                    "org_reftype": rec.get_reftype_misa_stock(),  # 2014
                    "org_reftype_name": "Nhập kho khác " + rec.name,
                    "currency_id": "VND",
                    "refdate": refdate,
                    "refno": rec.name,
                    "posted_date": posted_date,
                    "account_object_name": account_object_name,
                    "account_object_code": account_object_code,
                    "account_object_address": config.get_address(rec.partner_id),
                    "journal_memo": journal_memo,
                    "reftype": rec.get_reftype_misa_stock(),
                    "due_day": due_day,
                    "status": rec.get_status_misa(),
                    "payment_term_id": payment_term_id,
                    "payment_term_code": payment_term_code,
                    "payment_term_name": payment_term_name,
                    "detail": []
                }]
            }

            # === chi tiết sản pẩm  ===
            sort_order = 1
            for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                line.sudo()._compute_stock_misa_internal()
                if not line.product_id.default_code:
                    error_miss.append(f'Thiếu mã sản phẩm "{line.product_id.name}"')
                    continue

                stock_code = stock_name = ''
                if line.stock_misa_to:
                    _, stock_code, stock_name = config.get_stock_misa(stock=line.stock_misa_to)

                debit_account = line.misa_debit_account.code if line.misa_debit_account else None
                credit_account = line.misa_credit_account.code if line.misa_credit_account else None
                if not debit_account or not credit_account:
                    error_miss.append(f'Thiếu tài khoản kế toán cho sản phẩm "{line.product_id.name}"')
                    continue

                detail_line = {
                    "inventory_item_code": line.product_id.default_code,
                    "inventory_item_name": line.product_id.name,
                    "description": line.product_id.name,
                    "is_description": False,
                    "quantity": line.quantity,
                    "main_quantity": line.quantity,
                    "unit_name": line.product_uom.name or '',
                    "main_unit_name": line.product_uom.name or '',
                    "sort_order": sort_order,
                    "is_promotion": False,
                    "debit_account": debit_account,
                    "credit_account": credit_account,
                    "exchange_rate_operator": "*",
                    "main_convert_rate": 1,
                    "exchange_rate": 1,
                    "currency_id": "VND",
                    "status": rec.get_status_misa(),
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                }

                lot_no, expiry_date = config.get_info_lot_product(data=line)
                if lot_no: detail_line['lot_no'] = lot_no
                if expiry_date: detail_line['expiry_date'] = expiry_date

                body["voucher"][0]["detail"].append(detail_line)
                sort_order += 1

            if error_miss:
                raise UserError('\n'.join(error_miss))

            payload = json.dumps(body)
            response = requests.post(connect_url, headers=headers, data=payload, verify=True)

            if response.status_code == 200:
                data = response.json()
                if data.get('Success'):
                    rec.sudo().misa_status = 'synced'
                else:
                    if data.get('ErrorCode') == 'ExpiredToken':
                        rec.sync_misa_stock_picking_other_in(voucher_type, reset_token=True)
                    rec.sudo().misa_status = 'sync_failed'
            else:
                rec.sudo().misa_status = 'sync_failed'

            # === ghi log ===
            func = ','.join(rec.mapped('name'))
            self.env['ir.logging'].sudo().create({
                'name': 'sync_misa_stock_picking_other_in',
                'type': 'server',
                'message': f'headers: {headers}\ndata: {payload}\nResponse: {response.text}',
                'path': str(rec[0]._name),
                'func': func,
                'line': 1
            })

    # todo Đồng bộ hàng loạt
    def sync_misa_stock_picking_other_out(self, voucher_type=8, reset_token=False):
        """Đồng bộ Phiếu xuất kho khác → MISA (reftype=2022)"""
        # self.ensure_one()
        api_url, app_id, access_code, org_company_code, token = self.env[
            'res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if not (api_url and app_id and org_company_code and token):
            return

        config = self.env['res.config.settings'].sudo()
        TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

        for rec in self:
            refdate = config.get_datetime_format(rec.date_done or rec.create_date, TIMEZONE_VN)
            posted_date = config.get_datetime_format(rec.date_done or rec.create_date, TIMEZONE_VN)
            created_date = config.get_datetime_format(rec.create_date, TIMEZONE_VN)
            write_date = config.get_datetime_format(rec.write_date, TIMEZONE_VN)

            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {'X-MISA-AccessToken': token, 'Content-Type': 'application/json'}
            error_miss = []
            lang = self.env.lang or 'en_US'

            # === KIỂM TRA BẮT BUỘC ===
            if not rec.move_ids_without_package:
                error_miss.append('Thiếu thông tin chi tiết sản phẩm')

            # === KHO XUẤT ===
            stock_code = stock_name = ''
            if rec.location_id and rec.location_id.location_misa_id:
                stock_code = rec.location_id.location_misa_id.code
                stock_name = rec.location_id.location_misa_id.name
            else:
                error_miss.append(f'Chưa liên kết kho xuất "{rec.location_id.name}" với MISA')

            # === ĐỐI TƯỢNG (nếu có) ===
            account_object_name = rec.partner_id.name if rec.partner_id else ''

            # Lấy theo khách hàng mặc định nếu khách hàng hiện tại k có code
            if rec.partner_id.customer_code:
                account_object_code = rec.partner_id.customer_code
            elif rec.picking_type_id.default_customer:
                account_object_code = rec.picking_type_id.default_customer.customer_code
            else:
                account_object_code = ''

            # === NHÂN VIÊN ===
            employee_code, employee_name = config.get_employee_name(data=rec.user_id)

            # === GHI CHÚ ===
            journal_memo = ''
            pancake_source_id = ''
            if rec.note:
                soup = BeautifulSoup(rec.note, 'html.parser')
                journal_memo = soup.get_text()
            if rec.sale_id and rec.sale_id.pancake_order_id:
                pancake_source_id = rec.sale_id.pancake_source_id.name if rec.sale_id.pancake_source_id else ''
            journal_memo = account_object_name + " " + pancake_source_id


            # === ĐIỀU KHOẢN THANH TOÁN (nếu có SO) ===
            payment_term_id = payment_term_code = payment_term_name = ''
            due_day = 0
            if rec.sale_id:
                payment_term_id, payment_term_code, payment_term_name = config.get_payment_term_misa(
                    data=rec.sale_id.payment_term_id)
                due_day = rec.sale_id.number_of_days_owed or 0
            if rec.sale_id:
                account_object_code = rec.sale_id.pancake_order_id
            body = {
                "app_id": app_id,
                "org_company_code": org_company_code,
                "voucher": [{
                    "voucher_type": voucher_type,
                    "org_refid": rec.misa_id,
                    "org_refno": rec.origin or rec.name,
                    "org_reftype": rec.get_reftype_misa_stock(),  # 2022
                    "org_reftype_name": "Xuất kho khác " + rec.name,
                    "currency_id": "VND",
                    "refdate": refdate,
                    "refno": rec.name,
                    "posted_date": posted_date,
                    "created_date": created_date,
                    "created_by": rec.create_uid.name or '',
                    "modified_date": write_date,
                    "modified_by": rec.write_uid.name or '',
                    "account_object_name": account_object_name,
                    "account_object_code": account_object_code,
                    "account_object_address": config.get_address(rec.partner_id),
                    "employee_code": employee_code,
                    "employee_name": employee_name,
                    "journal_memo": journal_memo,
                    "reftype": rec.get_reftype_misa_stock(),
                    "due_day": due_day,
                    "status": rec.get_status_misa(),
                    "payment_term_id": payment_term_id,
                    "payment_term_code": payment_term_code,
                    "payment_term_name": payment_term_name,
                    "detail": []
                }]
            }

            sort_order = 1
            for line in rec.move_ids_without_package.filtered(lambda l: l.quantity > 0):
                line.sudo()._compute_stock_misa_internal()
                if not line.product_id.default_code:
                    error_miss.append(f'Thiếu mã sản phẩm "{line.product_id.name}"')
                    continue

                debit_account = line.misa_debit_account.code if line.misa_debit_account else None
                credit_account = line.misa_credit_account.code if line.misa_credit_account else None
                if not debit_account or not credit_account:
                    error_miss.append(f'Thiếu tài khoản kế toán cho sản phẩm "{line.product_id.name}"')
                    continue

                detail_line = {
                    "inventory_item_code": line.product_id.default_code,
                    "inventory_item_name": line.product_id.name,
                    "description": line.product_id.name,
                    "is_description": False,
                    "quantity": line.quantity,
                    "main_quantity": line.quantity,
                    "unit_name": line.product_uom.name or '',
                    "main_unit_name": line.product_uom.name or '',
                    "sort_order": sort_order,
                    "is_promotion": False,
                    "debit_account": debit_account,
                    "credit_account": credit_account,
                    "exchange_rate_operator": "*",
                    "main_convert_rate": 1,
                    "exchange_rate": 1,
                    "currency_id": "VND",
                    "status": rec.get_status_misa(),
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                }

                lot_no, expiry_date = config.get_info_lot_product(data=line)
                if lot_no: detail_line['lot_no'] = lot_no
                if expiry_date: detail_line['expiry_date'] = expiry_date

                body["voucher"][0]["detail"].append(detail_line)
                sort_order += 1

            if error_miss:
                raise UserError('\n'.join(error_miss))

            payload = json.dumps(body)
            response = requests.post(connect_url, headers=headers, data=payload, verify=True)

            if response.status_code == 200:
                data = response.json()
                if data.get('Success'):
                    rec.sudo().misa_status = 'synced'
                else:
                    if data.get('ErrorCode') == 'ExpiredToken':
                        rec.sync_misa_stock_picking_other_out(voucher_type, reset_token=True)
                    rec.sudo().misa_status = 'sync_failed'
            else:
                rec.sudo().misa_status = 'sync_failed'

            func = ','.join(rec.mapped('name'))
            self.env['ir.logging'].sudo().create({
                'name': 'sync_misa_stock_picking_other_out',
                'type': 'server',
                'message': f'headers: {headers}\ndata: {payload}\nResponse: {response.text}',
                'path': str(rec[0]._name),
                'func': func,
                'line': 1
            })

    def sync_misa_stock_picking_list(self):
        for rec in self:
            if rec.state not in ['done']:
                raise UserError(f'Đơn {rec.name} chưa được xác nhận là "Hoàn tất" nên không thể đồng bộ')
            else:
                rec.sync_misa_stock_picking()
        return True


    def convert_date_done(self):
        for rec in self:
            now = fields.Datetime.now()
            if rec.state == 'done' and  rec.scheduled_date < now:
                current_date =  rec.scheduled_date
                rec.write({
                    'date_done': current_date,
                })
                rec.move_line_ids.write({
                    'date': current_date,
                })
                valuation_layer_ids = self.env['stock.valuation.layer'].search(
                    [('id', 'in', (rec.move_ids).stock_valuation_layer_ids.ids)])
                for layer in valuation_layer_ids:
                    rec._cr.execute(
                        "UPDATE stock_valuation_layer SET create_date = '%s' WHERE id = %s" % (current_date,
                                                                                               layer.id))
                    if layer.sudo().account_move_id:
                        layer.account_move_id.sudo().write({
                            'date': current_date
                        })

    # Này sẽ conflix với luồng mặc định của Odoo DO tạo tay
    # @api.constrains('origin')
    # def check_origin(self):
    #     for record in self:
    #         if not record.origin:
    #             raise UserError('The code SO is none, cannot synchronize')
    def _compute_total_quantity(self):
        for picking in self:
            picking.total_quantity = sum(picking.move_ids.mapped('quantity'))

    def button_validate(self):
        for picking in self:
            if picking.location_id and picking.location_id.is_not_submit:
                raise UserError(
                    _(f'{picking.name} có vị trí nguồn \'{picking.location_id.name}\' là vị trí không lưu tồn kho cần chọn vị trí lưu kho khác'))
            if picking.location_dest_id and picking.location_dest_id.is_not_submit:
                raise UserError(
                    _(f'{picking.name} có vị trí đích \'{picking.location_dest_id.name}\' là vị trí kho ảo không lưu tồn kho cần chọn vị trí lưu kho khác'))


            if picking.picking_type_id.code == 'outgoing' and picking.sale_id:
                sale = picking.sale_id
                partner = sale.partner_id
                if partner.is_wholesaler:
                    if not sale.is_paid and not sale.account_payable:
                        if self.env.lang == 'en':
                            raise UserError(_(
                                "This WHOLESALE order is neither set for account payable nor fully paid.\n"
                                "Unable to determine the delivery order."
                            ))
                        else:
                            raise UserError(_(
                                "Đây là đơn hàng BÁN SỈ chưa được tích công nợ hoặc thanh toán đầy đủ.\n"
                                "Không thể xác định lệnh giao hàng. Vui lòng báo kế toán để xác nhận hoàn tất đơn hàng"
                            ))
            # picking.sync_misa_stock_picking()

        return super(StockPickingInherit, self).button_validate()

    @api.onchange('picking_type_id')
    def _onchange_picking_type_set_partner(self):
        for rec in self:
            if rec.picking_type_id and rec.picking_type_id.default_customer:
                rec.partner_id = rec.picking_type_id.default_customer

    @api.model
    def create(self, vals):
        if not vals.get('partner_id'):
            raise UserError(_('The delivery address can not be left blank!'))
        return super().create(vals)

    @api.depends('sale_id.misa_status','picking_type_id')
    def _compute_misa_status_related(self):
        for rec in self:
            if rec.picking_type_id.code == 'outgoing':
                rec.misa_status_related = rec.sale_id.misa_status
                rec.misa_status = rec.sale_id.misa_status

    def manual_create_backorder(self):
        self.ensure_one()
        moves = self.env['stock.move']
        for move in self.move_ids:
            if move.quantity < move.product_uom_qty:
                new_move = move.copy({
                    'product_uom_qty': move.product_uom_qty - move.quantity
                })
                new_move.state = 'draft'
                moves |= new_move
                move.write({
                    'product_uom_qty': move.quantity,
                })
        new_picking = self.copy({
            'move_ids': [(6, 0, moves.ids)],
            'backorder_id': self.id,
            'state': 'draft'
        })