from datetime import datetime, timedelta
from odoo import api, fields, models, _
import requests
import json
import pandas
from odoo.exceptions import UserError, ValidationError
import pytz
import traceback
import uuid
import re

# NAMESPACE_UUID = uuid.UUID('12345678-1234-5678-80b4-00c04fd430c8')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    api_url = fields.Char(string='API URL', config_parameter='advanced_sync_misa.api_url', default='https://actapp.misa.vn')
    app_id = fields.Char(string="APP ID", config_parameter='advanced_sync_misa.app_id')
    access_code = fields.Char(string="Access Code", config_parameter='advanced_sync_misa.access_code')
    org_company_code = fields.Char(string="Organization Company Code", config_parameter='advanced_sync_misa.org_company_code', default='maxbond_ketoan')
    misa_expired_time = fields.Char(string="Expired Time Misa Token", config_parameter='advanced_sync_misa.misa_expired_time')
    access_token_misa = fields.Char(string="Access Token", config_parameter='advanced_sync_misa.access_token_misa')
    branch_id = fields.Char(string="Branch ID", config_parameter='advanced_sync_misa.branch_id')
    limit_time = fields.Integer(string="Limit Time", config_parameter='advanced_sync_misa.limit_time', default=30)
    limit_fetch = fields.Integer(string="Limit Fetch", config_parameter='advanced_sync_misa.limit_fetch', default=1000)
    misa_discount_account = fields.Many2one('account.account.misa', string='Tài khoản chiết khấu', config_parameter='advanced_sync_misa.misa_discount_account')

    def sync_misa_get_token(self, reset_token=False):
        api_url = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.api_url', False)
        app_id = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.app_id', False)
        access_code = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.access_code', False)
        org_company_code = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.org_company_code', False)
        misa_expired_time = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.misa_expired_time', False)
        access_token_misa = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.access_token_misa', False)
        if not app_id:
            raise UserError(_('Missing application ID in Misa configuration.'))
        if not access_code:
            raise UserError(_('Missing access code in Misa configuration.'))
        if not org_company_code:
            raise UserError(_('Missing organization code in Misa configuration.'))
        if not api_url:
            raise UserError(_('Missing API URL in Misa configuration.'))
        try:
            ### Sử dụng token còn hạn
            if misa_expired_time and not reset_token:
                pandas_time = pandas.to_datetime(misa_expired_time).to_pydatetime()
                local = pytz.timezone('Asia/Ho_Chi_Minh')
                local_datetime = pandas_time.astimezone(local)
                utc_datetime = local_datetime.replace(tzinfo=None)
                utc_now = datetime.now()
                if utc_now < utc_datetime:
                    if access_token_misa:
                        return api_url, app_id, access_code, org_company_code, access_token_misa
            ### Token hết hạn hoặc token lỗi
            headers = {
                'Content-Type': 'application/json'
            }
            connect_url = api_url + '/api/oauth/actopen/connect'

            body = {
                "app_id": app_id,
                "access_code": access_code,
                "org_company_code": org_company_code,
            }
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)
            if response.status_code == 200:
                res = response.json()
                if 'Data' in res:
                    data_dict = json.loads(res['Data'])
                    access_token_misa = data_dict['access_token']
                    expired_time = data_dict['expired_time']
                    self.env['ir.config_parameter'].set_param('advanced_sync_misa.access_token_misa', access_token_misa)
                    self.env['ir.config_parameter'].set_param('advanced_sync_misa.misa_expired_time', expired_time)
            return api_url, app_id, access_code, org_company_code, access_token_misa
        except Exception as e:
            error_txt = traceback.format_exc() + str(e)
            headers = {
                'Content-Type': 'application/json'
            }
            connect_url = api_url + '/api/oauth/actopen/connect'

            body = {
                "app_id": app_id,
                "access_code": access_code,
                "org_company_code": org_company_code,
            }
            payload = json.dumps(body)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)
            if response.status_code == 200:
                res = response.json()
                if 'Data' in res:
                    data_dict = json.loads(res['Data'])
                    access_token_misa = data_dict['access_token']
                    expired_time = data_dict['expired_time']

                    self.env['ir.config_parameter'].set_param('advanced_sync_misa.access_token_misa', access_token_misa)
                    self.env['ir.config_parameter'].set_param('advanced_sync_misa.misa_expired_time', expired_time)

            ### Logging
            IrLogging = self.env['ir.logging']
            message = 'sync_misa_get_token\n' + str(body) + '\n\nResponse:\n' + str(response.text) + '\n\nerror_txt:\n' + error_txt
            IrLogging.sudo().create({'name': 'sync_misa_get_token_exception',
                                     'type': 'server',
                                     'message': message,
                                     'path': 'path',
                                     'func': 'func',
                                     'line': 1})
            return api_url, app_id, access_code, org_company_code, access_token_misa



    def encode_uuid(self, str_id):
        # Convert object_id to string
        str_code = str(str_id)
        # Generate a UUID using uuid5 with the namespace and product_id_str
        namespace_uuid = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.namespace_uuid', '12345678-1234-5678-80b4-00c04fd430c8')
        NAMESPACE_UUID = uuid.UUID(str(namespace_uuid))
        object_id = uuid.uuid5(NAMESPACE_UUID, str_code)
        if isinstance(object_id, tuple):
            return object_id[0]
        else:
            return str(object_id)

    def sync_misa_company_info(self, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env['res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and token:
            connect_url = api_url + '/apir/sync/actopen/get_company_info'
            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            data = {
                "app_id": app_id,
                "branch_id": None
            }
            payload = json.dumps(data)
            response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

            if response.status_code == 200:
                data = json.loads(response.text)
                if data['Success']:
                    content = json.loads(data['Data'])
                    mess = "Company Name: " + content['company_name'] + "\nTax Code: " + content['company_tax_code']
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Connection Successful.'),
                            'message': _(mess),
                            'sticky': True,
                            'type': 'success',
                        }
                    }
                else:
                    if data['ErrorCode'] == 'ExpiredToken':
                        print('Expired Token')
                        self.sync_misa_company_info(reset_token=True)
                    else:
                        raise ValidationError(data['ErrorMessage'])

            # else:
            #     self.sudo().misa_status = 'sync_failed'

            IrLogging = self.env['ir.logging']
            message = 'headers\n' + str(headers) + 'data\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
            IrLogging.sudo().create({'name': 'sync_misa_company_info',
                                     'type': 'server',
                                     'message': message,
                                     'path': 'path',
                                     'func': 'func',
                                     'line': 1})

    def get_employee_name(self, data):
        employee_code = employee_name = ""
        if data and data.employee_ids:
            if data.employee_ids:
                employee = data.employee_ids[0]
                if employee.employee_code_misa:
                    employee_code = employee.employee_code_misa
                    employee_name = employee.name
        return employee_code, employee_name

    def get_employee_name_detail(self, employee):
        employee_code = employee_name = ""
        if employee:
            employee_code = employee.employee_code_misa if employee.employee_code_misa else ''
            employee_name = employee.name
        return employee_code, employee_name

    def get_payment_term_misa(self, data):
        payment_term_id = payment_term_code = payment_term_name = ""
        if data:
            if data.payment_term_misa_id:
                payment = data.payment_term_misa_id

                payment_term_id = payment.misa_id
                payment_term_code = payment.code
                payment_term_name = payment.name
        return payment_term_id, payment_term_code, payment_term_name

    def get_datetime_format(self, data, timzone):
        str_date = ''
        if data:
            data = data + timedelta(hours=7)
            dt_string = data.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            str_date = dt_string + str(timzone)
        return str_date

    def get_address(self, partner):
        address = ''
        data = []
        if partner:
            if partner.street:
                data.append(partner.street)
            if partner.street2:
                data.append(partner.street2)
            if partner.city:
                data.append(partner.city)
            if partner.state_id:
                data.append(partner.state_id.name)
        if len(data) > 0:
            address = ', '.join(e for e in data)
        return address

    def get_inventory_item_type_to_misa(self, product_id):
        """
        0 Là Vật tư hàng hóa;
        1 Là thành phẩm;
        2 Là dịch vụ;
        3 Là Nguyên vật liệu
        """
        item_type = 0
        if product_id:
            if product_id.misa_features == 'component':
                item_type = 3
            elif product_id.misa_features == 'service':
                item_type = 2
            elif product_id.misa_features == 'end_products':
                item_type = 1
        return item_type

    def get_currency_id(self, data):
        currency = 'VND'
        if data and data.name:
            currency = data.name
        return currency

    def get_inventory_resale_type_id(self, data):
        """
            0 : Hàng hóa ký gửi, bán hộ
            1 : Hàng hóa giữ hộ, gia công
            2 : Hàng hóa bán hộ, ký gửi
        """
        type = 0
        return type

    def get_inventory_item_type(self, data):
        """
        Tính chất:
                0 Là Vật tư hàng hóa;
                1: Là thành phẩm;
                2 Là dịch vụ;
                3 là Nguyên vật liệu
        """
        misa_features = 'goods'
        if data == 1:
            misa_features = 'end_products'
        if data == 2:
            misa_features = 'service'
        if data == 3:
            misa_features = 'component'
        return misa_features

    def get_misa_account_by_code(self, data):
        account = self.env['account.account.misa'].sudo().search([('code', '=', data)], limit=1)
        return account.id if account else False

    def get_misa_country(self, name):
        country = self.env['res.country'].sudo().search([('name', 'ilike', name)], limit=1)
        return country.id if country else False

    def convert_company_type(self, name):
        company_type = 'person'
        if name and 'công ty' in name.lower():
            company_type = 'company'
        return company_type

    def get_stock_misa(self, stock):
        stock_id = stock_code = stock_name = ''
        if stock:
            stock_id = stock.misa_id
            stock_code = stock.code
            stock_name = stock.name
        return stock_id, stock_code, stock_name

    def get_info_lot_product(self, data):
        lot_no = ''
        expiry_date = False
        return lot_no, expiry_date

    def get_unit_by_misa(self, misa_id, misa_name):
        """
            Search unit by Misa ID or Name
        """
        unit = False
        if misa_name:
            unit = self.env['uom.uom'].sudo().search([('name', '=', misa_name)], limit=1)
        if not unit and  misa_id:
            unit = self.env['uom.uom'].sudo().search([('misa_id', '=', misa_id)], limit=1)
        return unit

    def get_stock_misa_by_misa_id(self, misa_id):
        """
            Search info stock misa by Misa ID
        """
        code = name = ''
        if misa_id:
            info = self.env['stock.location.misa'].sudo().search([('misa_id', '=', misa_id)], limit=1)
            if info:
                code = info.code
                name = info.name
        return code, name

    def update_syn_unit_by_misa(self, data):
        if data:
            if 'unit_name' in data and 'unit_id' in data:
                # Cập nhật mã Misa với Uom chưa có
                units = self.env['uom.uom'].sudo().search(['|', ('misa_id', '=', data['unit_id']), ('name', '=', data['unit_name'])], limit=1)
                if units:
                    for unit in units:
                        unit.sudo().write({'misa_id': data['unit_id']})
                        unit.sudo().write({
                            'name': data['unit_name'],
                            'misa_id': data['unit_id']
                        })
                else:
                    # Nếu đơn vị không tồn tại thì mới tạo mới
                    unit_search = self.env['uom.uom'].sudo().search([('name', '=ilike', data['unit_name'])])
                    if not unit_search:
                        unit_id = data['unit_id']
                        unit_name = data['unit_name']
                        if not unit_id or not unit_name:
                            return
                        # create_new_unit
                        self.env['uom.uom'].sudo().create({
                            'misa_id': data['unit_id'],
                            'name': data['unit_name'],
                            'category_id': self.env.ref('uom.product_uom_categ_unit').id,
                            'uom_type': 'bigger',
                            'ratio': 1.0,
                        })

    def validate_product_info(self, product_id):
        """ Kiểm tra thông tin sản phẩm và trả về lỗi nếu thiếu """
        lang = self.env.lang or 'en_US'
        if not product_id:
            raise UserError(_("Missing product information to generate lot/serial number.")
                            if lang == 'en_US'
                            else _("Thiếu thông tin sản phẩm để tạo mã Lô/seri."))
        if not product_id.default_code:
            raise UserError(_("Missing 'Internal Reference' product information to generate lot/serial number.")
                            if lang == 'en_US'
                            else _("Thiếu thông tin 'Mã nội bộ' sản phẩm để tạo mã Lô/seri."))
        if  product_id.default_code:
            vietnamese_regex = re.compile(
                r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]'
            )
            if vietnamese_regex.search(product_id.default_code or ''):
                raise ValidationError("\'Mã nội bộ\' sản phẩm không được chứa tiếng Việt có dấu.")

    def generate_serial_number_by_info(self, product_id, confirm_date, user_id, product_qty=1, weight=0):
        self.validate_product_info(product_id)
        serial_number = ''
        if confirm_date:
            serial_number = self.get_serial_number(product_id=product_id, confirm_date=confirm_date)
        data = {
            'product_id': product_id.id,
            'user_id': user_id,
            'name': serial_number,
            'barcode': serial_number,
            'product_qty': product_qty,
            'weight': weight,
        }
        lot_id = self.env['stock.lot'].sudo().create(data)
        return lot_id

    def get_serial_number(self, product_id, confirm_date):
        self.validate_product_info(product_id)
        prefix = f"{product_id.default_code}{confirm_date.strftime('%d%m')}{confirm_date.year % 100}"
        sequence = self.env['ir.sequence'].sudo().search([('code', '=', prefix)], limit=1)
        if not sequence:
            self.env['ir.sequence'].sudo().create({
                'name': 'Lot ' + str(product_id.default_code),
                'code': prefix,
                'prefix': prefix,
                'padding': 3,
                'number_increment': 1,
            })

        serial_number = self.env['ir.sequence'].next_by_code(prefix)

        # Kiểm tra xem serial_number có trùng với lot nào không
        seri_exist = self.env['stock.lot'].search([('name', '=', serial_number)], limit=1)
        if seri_exist:
            # Lấy các số serial hiện có bắt đầu với tiền tố đã cho
            list_name_series = self.env['stock.lot'].search([('name', 'like', f'{prefix}%')]).mapped('name')
            numbers = [int(item[len(prefix):]) for item in list_name_series if item[len(prefix):].isdigit()]

            if numbers:
                next_sequence = max(numbers) + 1
                sequence.sudo().write({'number_next': next_sequence})
                serial_number = self.env['ir.sequence'].next_by_code(prefix)

        return serial_number


    def get_pricelist_id(self, currency='VND'):
        pricelist_id = False
        if currency:
            currency_id = self.env['res.currency'].sudo().search([('name', '=', currency)], limit=1)
            if currency_id:
                pricelist_id = self.env['product.pricelist'].sudo().search([('currency_id', '=', currency_id.id)], limit=1)
        return pricelist_id

    def get_product_template_id_by_misa(self, code, name, uom_name):
        if code and name:
            product_template = self.env['product.product'].sudo().search(
                ['|',('default_code', '=', code) , ('name', 'like', name)], limit=1)
            if product_template:
                return product_template
            else:
                data = {
                    'default_code': code,
                    'name': name,
                }
                new_record = self.env['product.product'].sudo().create(data)
                if uom_name:
                    uom = self.env['uom.uom'].sudo().search([('name', '=', uom_name)], limit=1)
                    if uom:
                        new_record.uom_id = uom.id
                        new_record.uom_po_id = uom.id
                return new_record
        return False

    def get_tax_id_by_number(self, tax):
        if not isinstance(tax, (int, float)):
            return False
        # Truy vấn để tìm tax_id tương ứng
        tax_id = self.env['account.tax'].sudo().search([
            ('amount', '=', tax),
            ('type_tax_use', '=', 'sale')
        ], limit=1)

        return tax_id or False

    def get_res_user_by_code(self, misa_code):
        user_id = False
        if misa_code:
            employee_id = self.env['hr.employee'].sudo().search([('employee_code_misa', '=', misa_code)], limit=1)
            if employee_id and employee_id.user_id:
                user_id = employee_id.user_id
        return user_id


    def get_res_partner_by_code(self, customer_code, customer_name, employee_code):
        partner_id = False
        if customer_code:
            partner_id = self.env['res.partner'].sudo().search([('customer_code', '=', customer_code)], limit=1)
            if not partner_id and customer_name:
                user_id = self.get_res_user_by_code(misa_code=employee_code)
                new_partner_id = self.env['res.partner'].sudo().create({
                    'name': customer_name,
                    'customer_code': customer_code,
                    'customer_rank': 1,
                    'user_id': user_id.id if user_id else False,
                })
                partner_id = new_partner_id
        return partner_id

    def is_integer(self, value):
        if int(value) == value:
            return int(value)
        else:
            return value


    def update_note_attendance(self, time1, time2):
        note1 = 'Không'
        note2 = 'Không'
        if time1:
            note1 = (time1 + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M:%S")
        if time2:
            note2 = (time2 + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M:%S")
        return note1 +' -> '+note2

    def check_product_non_sync_misa(self, data):
        data_not_sync = []
        for product in data:
            if not product.misa_id:
                data_not_sync.append(product)
        return data_not_sync

    def check_res_partner_non_sync_misa(self, data):
        data_not_sync = []
        for res in data:
            if res.partner_id and not res.partner_id.misa_id:
                if res.partner_id not in data_not_sync:
                    data_not_sync.append(res.partner_id)
        return data_not_sync