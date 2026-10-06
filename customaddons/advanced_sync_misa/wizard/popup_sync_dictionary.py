from datetime import datetime, timedelta
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
import requests
import json
import time

# Hệ thống có dạng data có thể lấy về
DATA_SYNC = [('0', 'None'),
             ('1', 'Account object'),
             ('2', 'Inventory Item'),
             ('3', 'Stock'),
             ('4', 'Unit'),
             ('5', 'ACT Open Account'),
             ('6', 'ACT Open All Organization Unit'),
             ('8', 'Bank Account'),
             ('9', 'Project Work'),
             ('10', 'Job'),
             ('11', 'Payment Term'),
             ('12', 'Bank')
             ]

# Hệ thống có dạng data có thể lấy về - phiên bản 1
DATA_SYNC_VER1 = [('0', 'None'),
             ('1', 'Account object'),
             ('2', 'Inventory Item'),
             ('3', 'Stock'),
             ('4', 'Unit'),
             ('5', 'ACT Open Account'),
             ('6', 'Organization Unit'),
             ('11', 'Payment Term'),
             ]


class PopupSyncDictionary(models.TransientModel):
    _name = 'popup.sync.dictionary'

    # IMPORTANT: keep these as numeric, not strings, so autovacuum works correctly
    # Number of hours before transient records of this model are cleaned up
    _transient_max_hours = 1.0  # adjust if you want a different lifetime; use 0/False to disable time-based cleaning
    # Maximum number of records to keep; 0 or False disables count-based cleaning
    _transient_max_count = 0

    data_type = fields.Selection(DATA_SYNC_VER1, string='Data Type')

    limit = fields.Integer(string='Limit', default=1000)
    skip = fields.Integer(string='skip', default=0)

    last_sync_time = fields.Datetime(string='Last Sync Time')

    is_syn_inventory_balance = fields.Boolean(string='Sync Inventory Balance', default=False)

    location_id = fields.Many2one('stock.location', domain='[("usage", "=", "internal")]')

    def sync_misa_get_dictionary(self, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env[
            'res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and token and self.data_type:
            model = 'None'
            lang = self.env.lang or 'en_US'
            config = self.env['res.config.settings'].sudo()
            connect_url = api_url + '/apir/sync/actopen/get_dictionary'

            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            LIMIT_TIME = int(self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.limit_time', 30))
            LIMIT_FETCH = int(self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.limit_fetch', 1000))

            time_start = time.time()

            # now = config.get_datetime_format(datetime.now(), TIMEZONE_VN)

            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            data_type = int(self.data_type) if self.data_type else 0
            branch_id = None
            # skip = self.skip
            skip = 0
            take = self.limit
            last_sync_time = config.get_datetime_format(self.last_sync_time,
                                                        TIMEZONE_VN) if self.last_sync_time else None
            ### Kiểm tra dữ liệu hỗ trợ
            data_type_support = [1, 2, 3, 4, 5, 6, 11]
            if data_type not in data_type_support:
                if lang == 'vi_VN':
                    mess = 'Chưa hỗ trỡ đồng bộ dữ liệu.'
                else:
                    mess = 'Data retrieval is not yet supported.'
                raise UserError(mess)

            is_break = False

            # Mỗi lần call không quá giới hạn API
            step = take if take <= LIMIT_FETCH else LIMIT_FETCH
            while not is_break:
                data = {
                    "data_type": data_type,
                    "branch_id": branch_id,
                    "skip": skip,
                    "take": step,
                    "app_id": app_id,
                    "last_sync_time": last_sync_time
                }
                payload = json.dumps(data)
                response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

                ### Kiểm tra điều kiện dừng
                # if skip > take:
                #     is_break = True
                # Không call quá 30s
                if time.time() - time_start > LIMIT_TIME:
                    is_break = True
                # Skip qua số lượng bản ghi
                # if skip > take:
                #     is_break = True
                # Lấy dưới limit ko cần call lại
                # if take <= LIMIT_FETCH:
                #     is_break = True
                # else:
                skip += take
                print('Info: ', 'take: ' + str(take) + ' - ' + 'skip: ' + str(skip))
                len_contents = 0
                if response.status_code == 200:
                    data = json.loads(response.text)
                    if data['Success']:
                        contents = json.loads(data['Data'])
                        len_contents = len(contents)
                        print('Contents: ', len_contents)
                        ### Hết dữ liệu Break data
                        if len(contents) <= 0:
                            is_break = True

                        ### Điều khoản thanh toán
                        if data_type == 11:
                            model = 'account.payment.term.misa'
                            for cont in contents:

                                misa_id = cont['payment_term_id']
                                due_time = cont['due_time']
                                discount_time = cont['discount_time']
                                discount_percent = cont['discount_percent']
                                code = cont['payment_term_code']
                                name = cont['payment_term_name']
                                data = {
                                    "misa_id": misa_id,
                                    "due_time": due_time,
                                    "discount_time": discount_time,
                                    "discount_percent": discount_percent,
                                    "code": code,
                                    "name": name,
                                }
                                records = self.env[model].sudo().search([('code', '=', code)])
                                if records:
                                    for rec in records:
                                        rec.sudo().write(data)
                                else:
                                    self.env[model].sudo().create(data)
                        ### Cơ cấu tổ chức
                        if data_type == 6:
                            for cont in contents:
                                branch_id = cont['branch_id']
                                self.env['ir.config_parameter'].set_param('advanced_sync_misa.branch_id', branch_id)
                        ### Đơn vị tính
                        if data_type == 4:
                            for cont in contents:
                                misa_id = cont['unit_id']
                                unit_name = cont['unit_name']

                                unit = self.env['uom.uom'].search([('misa_id', '=', misa_id)], limit=1)

                                # if not unit:
                                #     unit = self.env['uom.uom'].search([
                                #         ('name', '=', unit_name),
                                #         ('category_id', '=', self.env.ref('uom.product_uom_categ_unit').id)
                                #     ], limit=1)

                                if not unit:
                                    unit = self.env['uom.uom'].sudo().create({
                                        'misa_id': misa_id,
                                        'name': unit_name,
                                        'category_id': self.env.ref('uom.product_uom_categ_unit').id,
                                        'uom_type': 'bigger',
                                        'ratio': 1.0,
                                    })
                                else:
                                    unit.sudo().write({
                                        'name': unit_name,
                                        'misa_id': misa_id
                                    })

                        ### Kho Misa
                        if data_type == 3:
                            model = 'stock.location.misa'
                            for cont in contents:
                                misa_id = cont['stock_id']
                                branch_id = cont['branch_id']
                                misa_inventory_code = cont['inventory_account'] if 'inventory_account' in cont else None
                                code = cont['stock_code']
                                name = cont['stock_name']
                                state = cont['state']
                                active = True if not cont['inactive'] else False
                                address = ""  # Data không có không đồng bộ
                                data = {
                                    'misa_id': misa_id,
                                    'branch_id': branch_id,
                                    'misa_inventory_code': misa_inventory_code,
                                    'code': code,
                                    'name': name,
                                    'state': state,
                                    'active': active,
                                }
                                if 'inventory_account' in cont:
                                    data['misa_account_inventory'] = config.get_misa_account_by_code(
                                        data=cont['inventory_account'])
                                if address:
                                    data["address"] = address
                                records = self.env[model].sudo().search(['|', ('misa_id','=',misa_id), ('code', '=', code)])
                                if records:
                                    for rec in records:
                                        rec.sudo().write(data)
                                else:
                                    self.env[model].sudo().create(data)
                        ### Hê thống tài khoản - ACTOpenAccount
                        if data_type == 5:
                            model = 'account.account.misa'
                            for cont in contents:
                                misa_id = cont['account_id']
                                code = cont['account_number']
                                name = cont['account_name']
                                name_vn = cont['account_name']
                                data = {
                                    'misa_id': misa_id,
                                    'code': code,
                                    'name': name,
                                    'name_vn': name_vn
                                }
                                if 'parent_id' in cont:
                                    data["parent_id"] = cont['parent_id']
                                records = self.env[model].sudo().search([('code', '=', code)])
                                if records:
                                    for rec in records:
                                        rec.sudo().write(data)
                                else:
                                    self.env[model].sudo().create(data)
                        ### Vật tư - Inventory Item.
                        if data_type == 2:
                            model = 'product.template'
                            for cont in contents:
                                self.sync_product_category(cont=cont)
                                misa_id = cont['inventory_item_id'] if 'inventory_item_id' in cont else ''
                                default_code = cont['inventory_item_code'] if 'inventory_item_code' in cont else ''
                                name = cont['inventory_item_name'] if 'inventory_item_name' in cont else ''
                                misa_features = config.get_inventory_item_type(data=cont['inventory_item_type'])
                                branch_id = cont['branch_id'] if 'branch_id' in cont else ''
                                description = cont['description'] if 'description' in cont else ''
                                description_sale = cont['sale_description'] if 'sale_description' in cont else ''
                                description_purchase = cont['purchase_description'] if 'purchase_description' in cont else ''
                                # Update info unit in Odoo
                                if 'unit_list' in cont:
                                    unit_info_list = json.loads(cont['unit_list'])
                                    if unit_info_list:
                                        for unit_data in unit_info_list:
                                            config.update_syn_unit_by_misa(data=unit_data)
                                # Update unit product
                                unit_misa_id = cont['unit_id'] if 'unit_id' in cont else False
                                unit_misa_name = cont['unit_name'] if 'unit_name' in cont else False
                                unit = config.get_unit_by_misa(misa_id=unit_misa_id, misa_name=unit_misa_name)
                                misa_uom = config.get_unit_by_misa(misa_id=unit_misa_id, misa_name=unit_misa_name)

                                data = {
                                    'misa_id': misa_id,
                                    'default_code': default_code,
                                    'name': name,
                                    'misa_features': misa_features,
                                    'branch_id': branch_id,
                                    'description': description,
                                    'description_sale': description_sale,
                                    'description_purchase': description_purchase,
                                    'misa_uom_id': misa_uom.id if misa_uom else False,
                                    'is_sync_misa': True,
                                }
                                if 'inventory_account' in cont:
                                    data['misa_account_inventory'] = config.get_misa_account_by_code(
                                        data=cont['inventory_account'])
                                if 'sale_account' in cont:
                                    data['misa_account_revenue'] = config.get_misa_account_by_code(
                                        data=cont['sale_account'])
                                if 'discount_account' in cont:
                                    data['misa_account_discount'] = config.get_misa_account_by_code(
                                        data=cont['discount_account'])
                                if 'sale_off_account' in cont:
                                    data['misa_account_sale'] = config.get_misa_account_by_code(
                                        data=cont['sale_off_account'])
                                if 'return_account' in cont:
                                    data['misa_account_return'] = config.get_misa_account_by_code(
                                        data=cont['return_account'])
                                if 'cogs_account' in cont:
                                    data['misa_account_expense'] = config.get_misa_account_by_code(
                                        data=cont['cogs_account'])
                                records = self.env[model].sudo().search([('default_code', '=', default_code)])
                                if records:
                                    for rec in records:
                                        rec.sudo().with_context(lang='en_US').write(data)
                                        rec.sudo().with_context(lang='vi_VN').write(data)
                                        if misa_uom:
                                            if rec.uom_id and rec.qty_available == 0 and rec.incoming_qty ==0 and rec.outgoing_qty ==0 and rec.sales_count == 0 and rec.purchased_product_qty == 0:
                                                move_count = self.env['stock.move'].sudo().search_count([
                                                    ('product_id', 'in', rec.product_variant_ids.ids),
                                                ])

                                                move_line_count = self.env['stock.move.line'].sudo().search_count([
                                                    ('product_id', 'in', rec.product_variant_ids.ids),
                                                ])

                                                if move_count == 0 and move_line_count == 0:
                                                    if misa_uom and rec.uom_id != misa_uom:
                                                        rec.sudo().write({
                                                            'uom_id': misa_uom.id,
                                                            'uom_po_id': misa_uom.id,
                                                        })

                                else:
                                    data['is_storable'] = True
                                    data['type'] = 'consu'
                                    if data['name'] and 'dịch vụ' in data['name'].lower():
                                        data['type'] = 'service'
                                        data['supplier_taxes_id'] = False
                                        data['taxes_id'] = False
                                    # Có đơn vị mới điền ko lấy theo mặc định của Odoo
                                    if unit:
                                        data['uom_id'] = unit.id
                                        data['uom_po_id'] = unit.id
                                    new_p = self.env[model].sudo().create(data)


                        ### Đối tương: khách hàng, NCC, Nhân viên - Account Object.
                        if data_type == 1:
                            model = 'res.partner'
                            for cont in contents:
                                misa_id = cont['account_object_id']
                                branch_id = cont['branch_id'] if 'branch_id' in cont else ''
                                name = cont['account_object_name'] if 'account_object_name' in cont else ''
                                company_type = config.convert_company_type(name=cont['account_object_name'])
                                customer_code = cont['account_object_code'] if 'account_object_code' in cont else ''
                                vat = cont['company_tax_code'] if 'company_tax_code' in cont else ''
                                street = cont['address'] if 'address' in cont else ''
                                country_id = config.get_misa_country(name=cont['country']) if 'country' in cont else ''
                                # contact_email = cont['contact_email'] if 'contact_email' in cont else ''
                                # tel = cont['tel'] if 'tel' in cont else ''
                                is_customer = cont['is_customer'] if 'is_customer' in cont else False
                                is_employee = cont['is_employee'] if 'is_employee' in cont else False
                                is_vendor = cont['is_vendor'] if 'is_vendor' in cont else False
                                data = {
                                    'misa_id': misa_id,
                                    'branch_id': branch_id,
                                    'name': name,
                                    'company_type': company_type,
                                    'customer_code': customer_code,
                                    'vat': vat,
                                    'street': street,
                                    'country_id': country_id,
                                    'is_sync_misa': True,
                                    'is_customer': is_customer,
                                    'is_employee': is_employee,
                                    'is_vendor': is_vendor,
                                    # 'phone' : tel if tel else '',
                                    # 'email': contact_email if contact_email else '',
                                }
                                if 'pay_account' in cont:
                                    data['pay_account'] = config.get_misa_account_by_code(data=cont['pay_account'])
                                if 'receive_account' in cont:
                                    data['receive_account'] = config.get_misa_account_by_code(
                                        data=cont['receive_account'])

                                is_customer = cont['is_customer'] if 'is_customer' in cont else False
                                is_vendor = cont['is_vendor'] if 'is_vendor' in cont else False
                                is_employee = cont['is_employee'] if 'is_employee' in cont else False

                                # Update thông tin khách hàng, NCC
                                records = self.env[model].sudo().with_context(active_test=False).search([
                                    ('customer_code', '=', customer_code), ('parent_id', '=', False)
                                ])
                                if records:
                                    for rec in records:
                                        rec.sudo().write(data)
                                else:
                                    if is_customer:
                                        data['customer_rank'] = 1
                                    if is_vendor:
                                        data['supplier_rank'] = 1
                                    # kiểm tra trùng tên thì cập nhật thông tin
                                    if is_vendor:
                                        venders = self.env[model].sudo().with_context(active_test=False).search([('name', 'ilike', data['name'])])
                                        if venders:
                                            for vender in venders:
                                                vender.sudo().write(data)
                                        else:
                                            self.env[model].sudo().create(data)
                                    else:
                                        self.env[model].sudo().create(data)
                                ### Update mã nhân viên nếu trùng tên
                                if is_employee and data['customer_code']:
                                    employee = self.env['hr.employee'].sudo().search([('name', 'ilike', data['name'])],
                                                                                     limit=1)
                                    if employee:
                                        employee.sudo().write({'employee_code_misa': data['customer_code']})
                                    else:
                                        self.env['hr.employee'].sudo().create([
                                            {
                                                'name': data['name'],
                                                'employee_code_misa': data['customer_code'],
                                                'mobile_phone' : data['phone'],
                                                'work_email': data['email'],
                                            }
                                        ])


                    else:
                        ### Dừng call api
                        is_break = True

                        if data['ErrorCode'] == 'ExpiredToken':
                            print('Expired Token')
                            # raise ValidationError(data['Expired Token'])
                            self.sync_misa_get_dictionary(reset_token=True)
                        else:
                            raise ValidationError(data['ErrorMessage'])
                else:
                    is_break = True
                print('finish: ', str(time.time() - time_start))
                IrLogging = self.env['ir.logging']
                message = ('headers\n' + str(headers) +
                           '\n\nfinish time\n ' + str(time.time() - time_start) +
                           '\n\ndata\n' + str(payload) +
                           '\n\nResponse:\n' + str(response.text))
                note = 'take: ' + str(take) + ' - ' + 'skip: ' + str(skip) + ' - ' + 'contents: ' + str(len_contents)
                IrLogging.sudo().create({'name': 'sync_misa_get_dictionary',
                                         'type': 'server',
                                         'message': message,
                                         'path': model,
                                         'func': note,
                                         'line': 1})

    def sync_product_category(self, cont):
        model = 'product.category.misa'
        if 'inventory_item_category_id_list' in cont:
            misa_id = cont['inventory_item_category_id_list']
            code = cont['inventory_item_category_misa_code_list']
            name = cont['inventory_item_category_name_list']
            code_list = cont['inventory_item_category_misa_code_list']
            data = {
                'misa_id': misa_id,
                'code': code,
                'name': name,
                'code_list': code_list,
            }
            records = self.env[model].sudo().search([('code', '=', code)])
            if records:
                for rec in records:
                    rec.sudo().write(data)
            else:
                self.env[model].sudo().create(data)

    def sync_misa_get_list_inventory_balance(self, reset_token=False):
        api_url, app_id, access_code, org_company_code, token = self.env[
            'res.config.settings'].sudo().sync_misa_get_token(reset_token=reset_token)
        if api_url and app_id and org_company_code and token:
            config = self.env['res.config.settings'].sudo()
            connect_url = api_url + '/apir/sync/actopen/get_list_inventory_balance'

            error_miss = []
            lang = self.env.lang or 'en_US'
            TIMEZONE_VN = self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.timezone_vn', '+07:00')
            LIMIT_TIME = int(self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.limit_time', 30))
            LIMIT_FETCH = int(self.env['ir.config_parameter'].sudo().get_param('advanced_sync_misa.limit_fetch', 1000))

            time_start = time.time()

            # now = config.get_datetime_format(datetime.now(), TIMEZONE_VN)

            headers = {
                'X-MISA-AccessToken': token,
                'Content-Type': 'application/json'
            }
            branch_id = None
            # skip = self.skip

            list_stock_id = []

            stock_id = stock_code = stock_name = ''
            if self.location_id and self.location_id.location_misa_id:
                stock_id, stock_code, stock_name = config.get_stock_misa(stock=self.location_id.location_misa_id)
                list_stock_id.append(stock_id)
            if self.location_id and not stock_id:
                if lang == 'vi_VN':
                    error_miss.append(
                        'Chưa liên kết thông tin kho \"' + self.location_id.name + '\" với kho có trên Misa')
                else:
                    error_miss.append(
                        'Inventory information for the \"' + self.location_id.name + '\" warehouse has not been synchronized with the warehouse in Misa.')

            if not self.location_id:
                stock_misa = self.env['stock.location.misa'].sudo().search([])
                if stock_misa:
                    for stock in stock_misa:
                        if stock.misa_id:
                            list_stock_id.append(stock.misa_id)

            if len(error_miss):
                mess = '\n'.join(error_miss)
                raise UserError(mess)

            for stock_id in list_stock_id:
                # Đồng bộ kho Misa
                stock_misa_code, stock_misa_name = config.get_stock_misa_by_misa_id(misa_id=stock_id)

                is_break = False
                skip = 0
                take = self.limit
                # Mỗi lần call không quá giới hạn API
                step = take if take <= LIMIT_FETCH else LIMIT_FETCH

                last_sync_time = config.get_datetime_format(self.last_sync_time,
                                                            TIMEZONE_VN) if self.last_sync_time else None
                while not is_break:
                    model = 'stock.quant'

                    data = {
                        "app_id": app_id,
                        "org_company_code": org_company_code,
                        "stock_id": stock_id,
                        "branch_id": branch_id,
                        "skip": skip,
                        "take": step,
                        "last_sync_time": last_sync_time
                    }

                    payload = json.dumps(data)
                    response = requests.request("POST", connect_url, headers=headers, data=payload, verify=True)

                    ### Kiểm tra điều kiện dừng
                    # if skip > take:
                    #     is_break = True
                    # Không call quá 30s
                    if time.time() - time_start > LIMIT_TIME:
                        is_break = True
                    # # Skip qua số lượng bản ghi
                    # if skip > take:
                    #     is_break = True
                    # # Lấy dưới limit ko cần call lại
                    # if take <= LIMIT_FETCH:
                    #     is_break = True
                    # else:
                    skip += take
                    print('Info: ', 'take: ' + str(take) + ' - ' + 'skip: ' + str(skip))
                    len_contents = 0
                    if response.status_code == 200:
                        data = json.loads(response.text)
                        if data['Success']:
                            contents = json.loads(data['Data'])
                            len_contents = len(contents)
                            for cont in contents:
                                product_misa_id = cont['inventory_item_id'] if 'inventory_item_id' in cont else None
                                stock_code = cont['stock_code'] if 'stock_code' in cont else None
                                stock_name = cont['stock_name'] if 'stock_name' in cont else None
                                quantity_balance = cont['quantity_balance'] if 'quantity_balance' in cont else 0
                                amount_balance = cont['amount_balance'] if 'amount_balance' in cont else 0
                                unit_price = cont['unit_price'] if 'unit_price' in cont else 0

                                if product_misa_id and stock_code:
                                    stock_quant_data = self.env['stock.quant'].sudo().search(
                                        [('product_id.misa_id', '=', product_misa_id),
                                         ('location_id.stock_misa_code', '=', stock_code)])
                                    if stock_quant_data:
                                        data_quant = stock_quant_data[0]
                                        if quantity_balance != data_quant.quantity_misa:
                                            data_quant.sudo().update({'quantity_misa': quantity_balance})

                            ### Hết dữ liệu Break data
                            if len(contents) <= 0:
                                is_break = True
                        else:
                            ### Dừng call api
                            is_break = True
                            if data['ErrorCode'] == 'ExpiredToken':
                                print('Expired Token')
                                # raise ValidationError(data['Expired Token'])
                                self.sync_misa_get_dictionary(reset_token=True)
                            else:
                                raise ValidationError(data['ErrorMessage'])
                    else:
                        ### Dừng call api
                        is_break = True

                    print('finish: ', str(time.time() - time_start))
                    IrLogging = self.env['ir.logging']
                    message = ('headers\n' + str(headers) +
                               '\n\nfinish time\n ' + str(time.time() - time_start) +
                               '\n\ndata\n' + str(payload) +
                               '\n\nResponse:\n' + str(response.text))
                    note = 'stock: ' + stock_misa_code + ' - ' + 'take: ' + str(take) + ' - ' + 'skip: ' + str(
                        skip) + ' - ' + 'contents: ' + str(len_contents)
                    IrLogging.sudo().create({'name': 'sync_misa_get_list_inventory_balance',
                                             'type': 'server',
                                             'message': message,
                                             'path': model,
                                             'func': note,
                                             'line': 1})

    @api.model
    def cron_fetch_misa_data(self):
        # fetch vat tu
        try:
            now = datetime.now()
            rec = self.sudo().create({
                'data_type': '1',
                'limit': 1000,
                'last_sync_time': datetime.combine(now - timedelta(days=1), now.time().min),
            })
            rec.sync_misa_get_dictionary()

            # fetch doi tuong
            rec.data_type = '2'
            rec.sync_misa_get_dictionary()
        except Exception as e:
            print('cron_fetch_misa_data: ', str(e))
            IrLogging = self.env['ir.logging']
            IrLogging.sudo().create({'name': 'cron_fetch_misa_data_error',
                                     'type': 'server',
                                     'message':  str(e),
                                     'path': '',
                                     'func': 'cron_fetch_misa_data',
                                     'line': 1})
