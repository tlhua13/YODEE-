import copy
from builtins import set

from odoo import api, fields, models, _
import requests
import json

from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, date
import time


class StockAuditMisa(models.Model):
    _name = 'stock.audit.misa'
    _rec_name = 'no'

    def default_get_no(self):
        last_rec = self.sudo().search([], limit=1, order='id desc')
        no = last_rec.id + 1 if last_rec else 1
        return f"KKK{no:06d}"

    def default_employee_ids(self):
        employee = False
        current_user = self.env.user
        if current_user and current_user.employee_ids:
            if current_user.employee_ids:
                employee = current_user.employee_ids[0]
        return employee

    no = fields.Char(default=default_get_no)

    location_id = fields.Many2one('stock.location', domain='[("usage", "=", "internal")]')
    about = fields.Text()
    audit_date = fields.Datetime(string='Audit Date')
    employee_ids = fields.Many2many('hr.employee', 'stock_audit_misa_employee_rel', string="Participants", default=default_employee_ids)

    ref_date = fields.Date(default=fields.Date.today)
    stock_quant_ids = fields.Many2many('stock.quant')
    stock_quant_sync = fields.One2many('stock.audit.misa.detail', 'stock_audit_misa_id', string='Chi tiết kiểm kê', copy=False)

    misa_id = fields.Char(string='Misa ID', compute='_compute_misa_id', store=True)

    misa_status = fields.Selection([('not_synced', 'Unsynchronized'),
                                    ('synced', 'Synchronized'),
                                    ('sync_failed', 'Synchronization Failed'),
                                    ], string='Misa Status', default='not_synced', copy=False)

    noti_status_misa = fields.Char(string='Noti Status', compute='compute_noti_status_misa')
    finish_sync_misa = fields.Boolean(string='Finish Sync Misa', default=False, copy=False)


    @api.depends('misa_status', 'finish_sync_misa')
    def compute_noti_status_misa(self, noti_callback=True):
        lang = self.env.lang or 'en_US'
        for rec in self:
            content = []
            if rec.misa_status not in ['not_synced']:
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
                    content.append('Audit inventory')
                else:
                    content.append('Kiểm Kê Kho')
            if len(content) > 0:
                content = ' - '.join(content)
                rec.noti_status_misa = '(' + content + ')'
            else:
                rec.noti_status_misa = ''

    @api.onchange('location_id')
    def onchange_location_id(self):
        for rec in self:
            stock_quant_ids = None
            if rec.location_id:
                if rec.location_id.quant_ids:
                    stock_quant_ids = rec.location_id.quant_ids.filtered(lambda l: l.inventory_quantity > 0)
            else:
                stock_quant_model = rec.env['stock.quant'].sudo()
                count_quant = stock_quant_model.search([('inventory_quantity', '>', 0)])
                if count_quant:
                    stock_quant_ids = [(6, 0, count_quant.ids)]
            rec.sudo().stock_quant_ids = stock_quant_ids

    @api.depends('no', 'ref_date')
    def _compute_misa_id(self):
        for rec in self:
            config = self.env['res.config.settings'].sudo()
            if rec.no:
                ref_date = rec.ref_date.strftime('%Y-%m-%d') if rec.ref_date else ''
                misa_id = config.encode_uuid(str_id='stock_audit_' + str(rec.id) + str(rec.no) + str(ref_date))
            else:
                misa_id = config.encode_uuid(str_id='stock_audit_' + str(rec.id))
            rec.misa_id = misa_id

    def sync_misa_stock_picking_in_audit(self, voucher_type=19, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        branch_id = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.branch_id', '')
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')

            ref_time = refdate = config.get_datetime_format(self.create_date, TIMEZONE_VN)
            audit_date = config.get_datetime_format(self.audit_date + timedelta(hours=7), TIMEZONE_VN)

            created_date = config.get_datetime_format(self.create_date, TIMEZONE_VN)
            write_date = config.get_datetime_format(self.write_date, TIMEZONE_VN)

            connect_url = api_url + '/apir/sync/actopen/save'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            error_miss = []
            lang = self.env.lang or 'en_US'
            org_reftype_name = ''
            all_locations = self.stock_quant_sync.mapped('location_id')
            if not all_locations:
                raise UserError("Thiếu thông tin kho để đồng bộ")
            for location in all_locations:
                # Đồng bộ kho Misa
                if self.location_id and not self.location_id.location_misa_id:
                    if lang == 'vi_VN':
                        error_miss.append('Chưa liên kết thông tin kho \"' + self.location_id.name + '\" với kho có trên Misa')
                    else:
                        error_miss.append('Inventory information for the \"' + self.location_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')

                title_stock_name = "Tất cả"
                if location and location.location_misa_id:
                    title_stock_name = location.location_misa_id.name

                audit_member = []
                if self.employee_ids:
                    for em in self.employee_ids:
                        full_name = representative = em.name
                        position = em.job_id.name if em.job_id else ''
                        info_em = {
                            "full_name": full_name,
                            "position": position,
                            "representative": representative,
                            "state": None
                        }
                        audit_member.append(info_em)

                journal_memo = self.about if self.about else ''

                parts = [
                    'stock_audit',
                    self.id,
                    location.id,
                ]
                if self.no:
                    ref_date = self.ref_date.strftime('%Y-%m-%d') if self.ref_date else ''
                    parts.append(ref_date)

                org_refid = config.encode_uuid(str_id='_'.join(map(str, parts)))
                org_refno = self.no
                org_reftype_name = "Kiểm kho " + self.no
                if location:
                    org_refno = self.no + ' - ' + location.name
                    org_reftype_name = "Kiểm kho " + self.no + ' - ' + location.name


                reftype = 2060  # Kiểm kê kho
                is_value_audit = True # Kiểm kê giá trị

                body = {
                    "app_id": app_id,
                    "org_company_code": org_company_code,
                    "voucher": [
                        {
                            "voucher_type": voucher_type,

                            "org_refid": org_refid,
                            "org_refno": org_refno,
                            "org_reftype": reftype,
                            "org_reftype_name": org_reftype_name,

                            "refdate": refdate,
                            "ref_time": ref_time,

                            "refno": self.no,

                            "audit_date": audit_date,
                            "is_value_audit": is_value_audit,

                            "created_date": created_date,
                            "created_by": self.create_uid.name if self.create_uid else '',
                            "modified_date": write_date,
                            "modified_by": self.write_uid.name if self.write_uid else '',

                            "journal_memo": journal_memo,

                            "reftype": reftype,
                            "branch_id": branch_id,

                            "stock_name": title_stock_name,
                            "audit_member": json.dumps(audit_member),
                            "detail": []
                        }],
                }

                # Thông tin chi tiết sản phẩm

                # Kiểm tra không đồng bộ sản phẩm chưa có trên Misa thì báo lỗi
                p_non = config.check_product_non_sync_misa(data=self.stock_quant_sync.mapped('product_id'), )
                if p_non:
                    product_names = '\n'.join(p.display_name for p in p_non)
                    raise UserError(
                        f"Vui lòng đồng bộ sản phẩm trước khi đồng bộ đơn đặt hàng. "
                        f"Sản phẩm chưa được đồng bộ với Misa:\n {product_names}"
                    )

                if self.stock_quant_sync:
                    lines_by_location = self.stock_quant_sync.filtered(
                        lambda l: l.location_id == location
                    )
                    if not lines_by_location:
                        continue
                    # Chia nhỏ danh sách lines thành các batch nhỏ hơn
                    for batch_index, batch_lines in enumerate(self.chunked(lines_by_location, 500), start=1):
                        # Cập nhật lại org_refno và org_reftype_name cho từng batch
                        org_refno = f"{self.no} - {location.name} - Batch {batch_index}"
                        org_reftype_name = f"Kiểm kho {self.no} - {location.name} - Batch {batch_index}"
                        body["voucher"][0]["org_reftype_name"] = org_reftype_name
                        body["voucher"][0]["org_refno"] = org_refno

                        # Cập nhật lại org_refid cho từng batch
                        parts_batch = [
                            'stock_audit',
                            self.id,
                            location.id,
                            batch_index,
                        ]
                        if self.no:
                            ref_date = self.ref_date.strftime('%Y-%m-%d') if self.ref_date else ''
                            parts_batch.append(ref_date)
                        org_refid_batch = config.encode_uuid(str_id='_'.join(map(str, parts_batch)))
                        body["voucher"][0]["org_refid"] = org_refid_batch

                        # Body mới cho từng batch
                        body_batch = copy.deepcopy(body)
                        body_batch["voucher"][0]["detail"] = []
                        sort_order = 1

                        for line in batch_lines:
                            if not line.product_id or not line.product_id.default_code:
                                error_miss.append(
                                    f"Thiếu mã sản phẩm \"{line.product_id.name}\""
                                )
                                continue

                            stock_id = stock_code = stock_name = ''
                            inventory_account = ''

                            if line.location_id.location_misa_id:
                                stock_id, stock_code, stock_name = config.get_stock_misa(
                                    stock=line.location_id.location_misa_id
                                )
                                stock_misa = line.location_id.location_misa_id
                                if stock_misa.misa_account_inventory:
                                    inventory_account = stock_misa.misa_account_inventory.code

                            quantity_on_book = line.quantity_on_book
                            quantity_audit = line.quantity_audit
                            diff_quantity = line.diff_quantity

                            unit_name = (
                                line.product_id.misa_uom_id.name
                                if line.product_id.misa_uom_id
                                else line.product_id.uom_id.name
                            )

                            amount_audit = (
                                line.value_stock_misa
                                if line.value_stock_misa > 0
                                else line.product_id.standard_price * quantity_audit
                            )

                            amount_on_book = line.product_id.standard_price * quantity_on_book
                            diff_amount = amount_audit - amount_on_book

                            data_sale_line = {
                                "inventory_item_code": line.product_id.default_code,
                                "inventory_item_name": line.product_id.name,
                                "unit_name": unit_name,
                                "main_unit_name": unit_name,
                                "sort_order": sort_order,
                                "exchange_rate_operator": "*",
                                "main_convert_rate": 1,
                                "exchange_rate": 1,
                                "stock_code": stock_code,
                                "stock_name": stock_name,
                                "inventory_account": inventory_account,
                                "quantity_on_book": quantity_on_book,
                                "quantity_audit": quantity_audit,
                                "diff_quantity": diff_quantity,
                                "execute_action": 1,
                                "amount_on_book": amount_on_book,
                                "amount_audit": amount_audit,
                                "diff_amount": diff_amount,
                            }

                            lot_no, expiry_date = config.get_info_lot_product(data=line)
                            if lot_no:
                                data_sale_line["lot_no"] = lot_no
                            if expiry_date:
                                data_sale_line["expiry_date"] = expiry_date

                            body_batch["voucher"][0]["detail"].append(data_sale_line)
                            sort_order += 1

                        if error_miss:
                            raise UserError('\n'.join(error_miss))

                        payload = json.dumps(body_batch)
                        response = requests.post(
                            connect_url,
                            headers=headers,
                            data=payload,
                            verify=True
                        )
                        if response.status_code == 200:
                            data = json.loads(response.text)
                            if data['Success']:
                                self.sudo().misa_status = 'synced'
                            else:
                                # Token hết hạn
                                if data['ErrorCode'] == 'ExpiredToken':
                                    print('Expired Token')
                                    self.sync_misa_stock_picking_in_audit(reset_token=True)
                                else:
                                    self.sudo().misa_status = 'sync_failed'
                        else:
                            self.sudo().misa_status = 'sync_failed'
                        IrLogging = self.env['ir.logging']

                        message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(
                            response.text)
                        IrLogging.sudo().create({'name': 'sync_misa_stock_picking_in_audit',
                                                 'type': 'server',
                                                 'message': message,
                                                 'path': str(self._name),
                                                 'func': org_reftype_name,
                                                 'line': 1})
                else:
                    if lang == 'vi_VN':
                        error_miss.append('Không tìm thấy dữ liệu tồn kho sản phẩm đã được kiểm kê.')
                    else:
                        error_miss.append('No inventory data found for inspected products.')
                if len(error_miss):
                    mess = '\n'.join(error_miss)
                    raise UserError(mess)

            view = self.env.ref('advanced_sync_misa.stock_audit_misa_form_view')
            return {
                'name': _('Kiểm kê (Misa)'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.audit.misa',
                'view_mode': 'form',
                'view_id': view.id,
                'res_id': self.id,
                'target': 'new',
            }

    # Chia nhỏ iterable thành các chunk có kích thước xác định
    def chunked(self, iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]
