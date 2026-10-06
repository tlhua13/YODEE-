import datetime
import json
import requests
import logging
import re
from odoo import models, fields, _, api
from odoo.exceptions import UserError
from .yodee_ir_logging import YodeeIrLogging
import time

_logger = logging.getLogger(__name__)

ORDER_STATUS_MAPPING = {'0': 'Mới',
                        '17': 'Chờ xác nhận',
                        '11': 'Chờ hàng',
                        '12': 'Chờ in',
                        '13': 'Đã in',
                        '20': 'Đã đặt hàng',
                        '1': 'Đã xác nhận',
                        '8': 'Đang đóng hàng',
                        '9': 'Chờ chuyển hàng',
                        '2': 'Đã gửi hàng',
                        '3': 'Đã nhận',
                        '16': 'Đã thu tiền',
                        '4': 'Đang hoàn',
                        '15': 'Hoàn một phần',
                        '5': 'Đã hoàn',
                        '6': 'Đã hủy',
                        '7': 'Đã xóa'}


class PancakeConnector(models.Model):
    _name = 'pancake.connector'
    _description = 'Pancake Connector'
    _rec_name = 'pancake_url'

    pancake_url = fields.Char(string='API URL', default='https://pos.pages.fm/api/v1')
    pancake_api_key = fields.Char(string="API Key")
    shop_id = fields.Char(string="Shop ID")

    # get/province
    pancake_url_province = fields.Char()
    param_is_new = fields.Boolean()
    # /get/districts
    pancake_url_districts = fields.Char()
    params_province_id = fields.Char()
    # /get/communes
    pancake_url_communes = fields.Char()
    params_district_id = fields.Char()
    limit_max = fields.Integer()
    limit_min = fields.Integer()
    #get customer
    customer_page_size = fields.Integer(default=50)
    customer_end_time_update = fields.Datetime(string='Product End Time Update')
    customer_start_time_update = fields.Datetime(string='Product Start Time Update')
    customer_page_number = fields.Integer(default=1)
    customer_duration = fields.Integer(string='Duration(minutes)', default=15)
    customer_time = fields.Boolean(string='Using Param Time', default=True)
    # get order
    order_date_from = fields.Datetime(string='Order Date From')
    order_date_to = fields.Datetime(string='Order Date To')
    order_duration = fields.Integer(string='Duration(minutes)', default=30)
    order_time = fields.Boolean(string='Using Param Time', default=True)
    order_page_size = fields.Integer(string='Order Page Size', default=50)
    order_page = fields.Integer(string='Order Page', default=1)
    order_break_day = fields.Integer(string='Beark Day', default=30, help="Giới hạn chỉ lấy đơn hàng trong khoảng X ngày gần nhất để tránh đồng bộ đơn hàng cũ quá nhiều")
    list_status = fields.Char(string='status', default='1')
    pancake_order_id = fields.Char(string='Pancake order id')
    # 1,2,3,4,5,8,9,11,12,13,15,16,17,20
    # Bỏ qua 0 ,6, 7


    # get product
    product_date_from = fields.Datetime(string='Product Date From')
    product_date_to = fields.Datetime(string='Product Date To')
    product_duration = fields.Integer(string='Duration(minutes)', default=30)
    product_time = fields.Boolean(string='Using Param Time', default=True)
    product_page_size = fields.Integer(string='Product Page Size', default=50)
    product_page = fields.Integer(string='Product Page', default=1)
    # sync product
    page_number = fields.Integer(default=0)
    page_size = fields.Integer(default=0)
    sync_stock_done = fields.Boolean(default=False)
    last_sync_time = fields.Datetime('Last Sync Time')
    sync_product_date_from = fields.Datetime(string='Sync Product Date From')
    sync_product_date_to = fields.Datetime(string='Sync Product Date To')

    timeout_minutes_order = fields.Integer(string="Timeout (phút)", default=10,help="Thời gian tối đa chạy cron, nếu vượt sẽ ngắt và lần sau tiếp tục")
    timeout_minutes_product = fields.Integer(string="Timeout (phút)", default=10,help="Thời gian tối đa chạy cron, nếu vượt sẽ ngắt và lần sau tiếp tục")

    def _cron_sync_customer_from_pancake(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
        start_time_updated_at = pancake_connector.customer_start_time_update
        end_time_updated_at = pancake_connector.customer_end_time_update
        page_size = pancake_connector.customer_page_size
        page_number = pancake_connector.customer_page_number

        res_partners = self.get_customer_from_pancake(start_time_updated_at, end_time_updated_at, page_size, page_number)
        self.env.cr.commit()
        return True

    @api.onchange('customer_start_time_update', 'customer_end_time_update')
    def validate_customer_time(self):
        for rec in self:
            if rec.customer_start_time_update and rec.customer_end_time_update and rec.customer_start_time_update > rec.customer_end_time_update:
                raise UserError(_('Thời gian bắt đầu phải nhỏ hơn thời gian kết thúc'))
            if rec.customer_start_time_update and rec.customer_start_time_update > datetime.datetime.now():
                raise UserError(_('Thời gian bắt đầu không được lớn hơn thời gian hiện tại'))

    def button_get_customer_from_pancake(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
        start_time_updated_at = pancake_connector.customer_start_time_update
        end_time_updated_at = pancake_connector.customer_end_time_update
        # print(start_time_updated_at)
        page_size = pancake_connector.customer_page_size
        page_number = pancake_connector.customer_page_number
        if not page_size or not page_number:
            raise UserError(_('Vui lòng nhập page size và page number'))

        res_partners = self.get_customer_from_pancake(start_time_updated_at, end_time_updated_at, page_size,
                                                      page_number)
        if isinstance(res_partners, dict):
            return res_partners

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Customer information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def get_customer_from_pancake(self, start_time_updated_at, end_time_updated_at, page_size, page_number):
        date_now = datetime.datetime.now()
        start_time = time.perf_counter()
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
        duration = pancake_connector.customer_duration
        customer_time = pancake_connector.customer_time
        page_size = page_size or 50
        end_time_param = True
        # Xử lý thời gian bắt đầu và kết thúc
        if not start_time_updated_at and not end_time_updated_at:
            start_time_updated_at = date_now
            end_time_updated_at = date_now + datetime.timedelta(minutes=duration)

        elif not start_time_updated_at:
            start_time_updated_at = end_time_updated_at
            end_time_updated_at = end_time_updated_at + datetime.timedelta(minutes=duration)

        elif not end_time_updated_at:
            end_time_updated_at = start_time_updated_at + datetime.timedelta(minutes=duration)

        elif start_time_updated_at > end_time_updated_at or start_time_updated_at > date_now:
            end_time_param = False
            start_time_updated_at = date_now
            end_time_updated_at = date_now + datetime.timedelta(minutes=duration)

        # pancake_connector.customer_start_time_update = start_time_updated_at
        # pancake_connector.customer_end_time_update = end_time_updated_at
        # Gán lại vào object
        CRON_TIME_LIMIT = (duration - 3) * 60
        time_limit_over = False

        def call_api_customer(start_time_updated_at, end_time_updated_at, page_size ,page_number, end_time_param=None):
            pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
            url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/customers"
            start_time_updated_at = int(start_time_updated_at.timestamp())
            end_time_updated_at = int(end_time_updated_at.timestamp())
            params = {
                "api_key": pancake_connector.pancake_api_key,
                "page_size": page_size,
                'page_number': page_number,
            }
            if customer_time:
                if end_time_param:
                    params.update({
                        "start_time_updated_at": start_time_updated_at,
                        "end_time_updated_at": end_time_updated_at,
                    })
                else:
                    params['start_time_updated_at'] = start_time_updated_at
            headers = {"Content-Type": "application/json"}
            try:
                response = requests.request("GET", url, headers=headers, params=params)
                response.raise_for_status()
                datas = response.json()
                logging = self.env['yodee.ir.logging'].sudo()
                logging.log_outgoing_request(response)
            except Exception as e:
                _logger.error(f"Unexpected Error: {str(e)}")
                return str(e)
            return datas

        datas = call_api_customer(start_time_updated_at, end_time_updated_at, page_size, page_number, end_time_param)
        if isinstance(datas, str):
             return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('An unexpected error occurred: %s') % datas,
                        'type': 'danger',
                        'sticky': True,
                    }
                }
        total_pages = datas.get('total_pages')
        res_partners = self.env['res.partner']
        customers = datas.get('data', [])
        res_partners |= self.process_data_customer(customers=customers)
        try:
            while total_pages > page_number:
                page_number += 1
                datas = call_api_customer(start_time_updated_at, end_time_updated_at, page_size, page_number)
                if isinstance(datas, str):
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Error'),
                            'message': _('An unexpected error occurred: %s') % datas,
                            'type': 'danger',
                            'sticky': True,
                        }
                    }
                customers = datas.get('data', [])
                res_partners |= self.process_data_customer(customers=customers)
                #check qua time limit luu lai gia tri lan sau call lai
                if time.perf_counter() - start_time >= CRON_TIME_LIMIT:
                    pancake_connector.write({
                        'customer_start_time_update': start_time_updated_at,
                        'customer_end_time_update': end_time_updated_at,
                        'customer_page_size': page_size,
                        'customer_page_number': page_number
                    })
                    time_limit_over = True
                    self.env.cr.commit()
                    break
        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        # done
        if not time_limit_over:
            if (pancake_connector.customer_start_time_update and pancake_connector.customer_end_time_update and
                    pancake_connector.customer_start_time_update > date_now or
                    pancake_connector.customer_start_time_update > pancake_connector.customer_end_time_update):
                pancake_connector.write({
                    'customer_start_time_update': pancake_connector.customer_end_time_update,
                    'customer_end_time_update': date_now,
                    'customer_page_size': page_size,
                    'customer_page_number': 1
                })
            else:
                pancake_connector.write({
                    'customer_start_time_update': end_time_updated_at,
                    'customer_end_time_update': date_now,
                    'customer_page_size': page_size,
                    'customer_page_number': 1
                })

        return res_partners

    def format_phone(self, phone):
        _RE_ONLY_DIGITS = re.compile(r'^\d+$')
        s = str(phone).strip()
        plus = s.startswith('+')
        if plus:
            s = s[1:]
        # Giữ chỉ chữ số
        digits = re.sub(r'\D', '', s)  # xóa mọi ký tự không phải chữ số
        if not _RE_ONLY_DIGITS.match(digits):
            return ''
        if digits.startswith('84') and len(digits) == 11 + 1:  # 84 + 9? actually 84 + 9? Wait below simpler check
            pass
        if len(digits) == 10 and digits.startswith('0'):
            normalized = digits
        elif len(digits) == 11 and digits.startswith('84'):
            # 84 + 9 digits -> convert to 0 + last 9 digits (-> total 10)
            normalized = '0' + digits[2:]
        elif len(digits) == 12 and digits.startswith('084'):
            # rare: someone nhập 084XXXXXXXXX -> bo 0
            normalized = digits[1:]
            if not (len(normalized) == 11 and normalized.startswith('84')):
                normalized = ''
            normalized = '0' + normalized[2:]
        else:
            normalized = ''
        # Final safety: must be 10 digits and start with 0
        if len(normalized) != 10 or not normalized.startswith('0'):
            normalized = ''
        return normalized

    def process_data_customer(self, customers):
        res_partners = self.env['res.partner']
        record = False
        for data in customers:
            phone = data.get('phone_numbers')[0] if data.get('phone_numbers') else ''
            #format thanh sdt chuan
            phone = self.format_phone(phone)
            pancake_id = data.get('id')

            shop_customer_addresses = data.get('shop_customer_addresses') or []
            address = shop_customer_addresses[0] if shop_customer_addresses else {}

            province_code = address.get('province_id')  # "207"

            province = False
            if province_code:
                province = self.env['pancake.provinces'].sudo().search([('new_id', '=', province_code)], limit=1)

            commune_code = address.get('commune_id')
            commune = False
            if commune_code:
                commune = self.env['pancake.communes'].sudo().search([('new_id', '=', commune_code)], limit=1)

            note = "Đây là liên hệ có trùng số điện thoại với liên hệ có ID là <x>, có thể được tạo ra do trên pancake đang tồn tại 2 khách hàng khác nhau có Số điện thoại giống nhau. Vui lòng thay đổi số điện thoại trước khi bỏ lưu trữ khách hàng này!"
            shop_customer_addresses = data.get('shop_customer_addresses') or []
            # Lấy record cha
            first_address = shop_customer_addresses[0] if shop_customer_addresses else {}
            res_partner_data = {
                'pancake_customer_id': data.get('customer_id'),
                # 'pancake_id': pancake_id,
                'name': data.get('name'),
                'email': data.get('emails')[0] if data.get('emails') else '',
                'phone': phone or '',
                'pancake_full_address': first_address.get('full_address', '') if first_address else '',
                'pancake_country_code': first_address.get('country_code', '') if first_address else '',
                'pancake_category_id': data.get('tags')[0] if data.get('tags') else '',
                'pancake_assigned_user_id': data.get('assigned_user_id') or '',
                'pancake_gender': data.get('gender') or '',
                'pancake_order_json': data,
                'is_sync_pancake': True,
                'pancake_country_state_code': province.id if province else False,
                'pancake_country_ward_code': commune.id if commune else False,
            }
            if phone:
                record = self.env['res.partner'].search([('pancake_id', '=', pancake_id), ('phone', '=', phone)])
                record_duplicate_id = self.env['res.partner'].search([('pancake_id', '=', pancake_id), ('phone', '!=', phone)])
                record_duplicate_phone = self.env['res.partner'].search([('pancake_id', '!=', pancake_id), ('phone', '=', phone)])

                #trung id, sdt => update
                if record:
                    record.write(res_partner_data)
                #trung id khac sdt => tao moi + archive
                elif record_duplicate_id:
                    res_partner_data['pancake_note'] = f'Trùng ID: {pancake_id} – Khác số điện thoại: sdt cũ:{record_duplicate_id[0].phone} - sdt mới:{phone} '
                    record_duplicate_id.write(res_partner_data)
                    record = record_duplicate_id[0]
                #khac id, trung sdt => tao moi + archive + note trung
                elif record_duplicate_phone:
                    for dup in record_duplicate_phone:
                        # Archive partner cũ
                        dup_vals = res_partner_data.copy()
                        dup_vals.update({
                            'pancake_id': pancake_id,
                            'active': False,
                            'pancake_note': f'Khác ID: id cũ: {dup.pancake_id}, id mới:{pancake_id} – Trùng số điện thoại: {phone},' + note,
                        })

                        # Archive tất cả các contact con
                        children = self.env['res.partner'].sudo().search([('parent_id', '=', dup.id)])
                        for child in children:
                            child.sudo().write({'active': False})

                        dup.sudo().write(dup_vals)

                    # Tạo partner mới với dữ liệu Pancake hiện tại
                    res_partner_data['pancake_id'] = pancake_id
                    record = self.env['res.partner'].sudo().create(res_partner_data)

                # khacs id, khac sdt => tao moi
                else:
                    res_partner_data['pancake_id'] = pancake_id
                    record = self.env['res.partner'].sudo().create(res_partner_data)
            else:
                res_partner_data['pancake_id'] = pancake_id

                res_partner_pancake= self.env['res.partner'].search([('pancake_id', '=', pancake_id)],limit =1)
                if not res_partner_pancake:
                    record = self.env['res.partner'].sudo().create(res_partner_data)
                else:
                    res_partner_pancake.sudo().write(res_partner_data)
                    record = res_partner_pancake
            # Tạo và update contact address(con của partner cha)
            shop_customer_addresses = data.get('shop_customer_addresses') or []
            if record and shop_customer_addresses:
                for address in shop_customer_addresses[1:]:
                    addr_phone = self.format_phone(address.get('phone_number'))
                    addr_full = address.get('full_address')

                    # bỏ qua địa chỉ rỗng
                    if not addr_full or addr_full.strip() in ['', ',', ', ']:
                        continue

                    addr_vals = {
                        'parent_id': record.id,
                        'type': 'delivery',  # địa chỉ phụ -> delivery address
                        'name': address.get('full_name') or record.name,
                        'phone': addr_phone,
                        'street': address.get('address') or '',
                        'pancake_full_address': addr_full or '',
                        'active': True,
                        'is_sync_pancake': True,
                    }

                    # tìm địa chỉ cũ
                    existing_contact = self.env['res.partner'].sudo().search([
                        ('parent_id', '=', record.id),
                        ('phone', '=', addr_phone)
                    ], limit=1)

                    if existing_contact:
                        existing_contact.write(addr_vals)
                    else:
                        self.env['res.partner'].sudo().create(addr_vals)
                    # self.env['res.partner'].sudo().create(addr_vals)

            if record:
                res_partners |= record
        return res_partners

    def get_address_from_pancake(self):
        provinces = self.get_province_from_pancake()
        if isinstance(provinces, dict):
            raise provinces
        for province in provinces:
            districts = self.get_district_from_pancake(province)
            if isinstance(districts, dict):
                return districts
            for district in districts:
                communes = self.get_geo_communes_from_pancake(district, province)
                if isinstance(communes, dict):
                    return communes
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shop information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def button_get_province_from_pancake(self):
        provinces = self.get_province_from_pancake()
        if isinstance(provinces, dict):
            raise provinces
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shop information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def button_get_communes_from_pancake(self):
        if not self.limit_max:
            raise UserError('Vui lòng chọn limit max')
        if self.limit_max < self.limit_min:
            raise UserError('Limit max phải lớn hơn min')

        districts = self.env['pancake.districts'].search([])
        if not districts:
            raise UserError('Vui lòng đồng bộ quận huyện trước')

        if self.limit_max > len(districts) or self.limit_min < 0:
            raise UserError(f'Vui lòng chọn trong khoảng từ 0 tới {len(districts)}')

        for district in districts[self.limit_min:self.limit_max]:
            communes = self.get_geo_communes_from_pancake(district, district.pancake_provinces_id)
            if isinstance(communes, dict):
                return communes
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shop information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def button_get_districts_from_pancake(self):
        # provinces = self.env['pancake.provinces'].search([])
        provinces = self.env['pancake.provinces'].search([])
        if not provinces:
            raise UserError('vui lòng đông bộ tỉnh trước')
        for province in provinces:
            districts = self.get_district_from_pancake(province)
            if isinstance(districts, dict):
                return districts
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shop information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def get_province_from_pancake(self):
        # get province
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
        url = pancake_connector.pancake_url + pancake_connector.pancake_url_province
        params = {
            'api_key': pancake_connector.pancake_api_key,
            'shops': pancake_connector.shop_id,
            'all': 'true',
        }
        provinces = self.env['pancake.provinces']
        try:
            response = requests.request("GET", url, params=params)
            response.raise_for_status()
            datas = response.json()
            for data in datas.get('data', []):
                record = self.env['pancake.provinces'].search([('api_province_id', '=', data.get('id'))])
                province_data = {
                    'country_code': data.get('country_code'),
                    'name': data.get('name'),
                    'name_en': data.get('name_en'),
                    'new_id': data.get('new_id'),
                    'region_type': data.get('region_type'),
                    'is_new_province': False if data.get('new_id') else True,
                }
                if record:
                    record.write(province_data)
                else:
                    province_data['api_province_id'] = data.get('id')
                    record = self.env['pancake.provinces'].sudo().create(province_data)
                provinces |= record
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)
        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        return provinces

    def get_district_from_pancake(self, province=None):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + pancake_connector.pancake_url_districts
        params = {
            'api_key': pancake_connector.pancake_api_key,
            'shops': pancake_connector.shop_id,
        }
        if province:
            params['province_id'] = province.api_province_id
        try:
            response = requests.request("GET", url, params=params)
            response.raise_for_status()
            datas = response.json()
            districts = self.env['pancake.districts']
            for data in datas.get('data', []):
                record = self.env['pancake.districts'].search([('api_district_id', '=', data.get('id'))])
                districts_data = {
                    'name': data.get('name'),
                    'name_en': data.get('name_en'),
                    'postcode': data.get('postcode'),
                    'api_province_id': data.get('province_id'),
                    'pancake_provinces_id': province.id,
                }
                if record:
                    record.sudo().write(districts_data)
                else:
                    districts_data['api_district_id'] = data.get('id')
                    record = self.env['pancake.districts'].sudo().create(districts_data)
                districts |= record
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        return districts

    # get communes
    def get_geo_communes_from_pancake(self, district=None, province=None):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + pancake_connector.pancake_url_communes
        params = {
            'api_key': pancake_connector.pancake_api_key,
            'shops': pancake_connector.shop_id,
        }
        if district:
            params['province_id'] = district.api_province_id
        if province:
            params['district_id'] = district.api_district_id
        try:
            response = requests.request("GET", url, params=params)
            response.raise_for_status()
            # data = response.json()
            datas = response.json()
            communes = self.env['pancake.communes']
            for data in datas.get('data', []):
                record = self.env['pancake.communes'].search([('api_communes_id', '=', data.get('id'))])
                communes_data = {
                    'api_district_id': data.get('district_id'),
                    'name': data.get('name'),
                    'name_en': data.get('name_en'),
                    'new_id': data.get('new_id'),
                    'postcode': data.get('postcode'),
                    'api_province_id': data.get('province_id'),
                    'pancake_district_id': district.id,
                    'pancake_provinces_id': province.id,
                }
                if record:
                    record.sudo().write(communes_data)
                else:
                    communes_data['api_communes_id'] = data.get('id')
                    record = self.env['pancake.communes'].sudo().create(communes_data)
                communes |= record
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        return communes

    def button_get_new_communes_from_pancake(self):
        provinces = self.env['pancake.provinces'].search([('is_new_province', '=', True)])
        for province in provinces:
            communes = self.get_new_geo_communes_from_pancake(province)
            if isinstance(communes, dict):
                return communes
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Shop information retrieved successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    # get new communes
    def get_new_geo_communes_from_pancake(self, province=None):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + pancake_connector.pancake_url_communes
        params = {
            'api_key': pancake_connector.pancake_api_key,
            'shops': pancake_connector.shop_id,
        }
        if province and province.is_new_province:
            params['province_id'] = province.api_province_id
        try:
            response = requests.request("GET", url, params=params)
            response.raise_for_status()
            data = response.json()
            datas = response.json()
            communes = self.env['pancake.communes']
            for data in datas.get('data', []):
                record = self.env['pancake.communes'].search([('api_communes_id', '=', data.get('id'))])
                communes_data = {
                    'api_district_id': data.get('district_id'),
                    'name': data.get('name'),
                    'name_en': data.get('name_en'),
                    'new_id': data.get('new_id'),
                    'postcode': data.get('postcode'),
                    'api_province_id': data.get('province_id'),
                    'is_communes_new': True,
                    # 'pancake_district_id': ,
                    'pancake_provinces_id': province.id,
                }
                if record:
                    record.sudo().write(communes_data)
                else:
                    communes_data['api_communes_id'] = data.get('id')
                    record = self.env['pancake.communes'].sudo().create(communes_data)
                communes |= record
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        return communes

    def action_open_pancake_connector(self):
        # res_id = self.env['pancake.connector'].search([], limit=1).id
        res_id = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False).id
        form_view = self.env.ref('advanced_sync_pancake.pancake_connector_form_view').id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pancake Connector',
            'res_model': 'pancake.connector',
            'view_mode': 'form',
            'views': [(form_view, 'form')],
            'res_id': res_id,
            'target': 'current',
        }

    def get_info_pancake(self):
        """
        Get shop information from Pancake API and log to yodee.ir.logging
        """
        try:
            api_url = self.pancake_url
            api_key = self.pancake_api_key

            if not api_url or not api_key:
                raise ValueError("API URL and API Key must be configured")

            # Build the endpoint URL
            url = f"{api_url}/shops"
            params = {'api_key': api_key}

            # Make the GET request
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Parse response
            data = response.json()
            if "shops" in data:
                for shop in data["shops"]:
                    shop_id = shop['id']
                    pancake = self.env['pancake.shop'].sudo().search([('shop_id', '=', shop_id)])
                    if pancake:
                        pancake.write({
                            'name': shop['name'],
                            'currency_text': shop['currency'],
                            'avatar_url': shop['avatar_url'],
                        })
                    else:
                        self.env['pancake.shop'].sudo().create({
                            'name': shop['name'],
                            'shop_id': shop_id,
                            'currency_text': shop['currency'],
                            'avatar_url': shop['avatar_url'],

                        })

            # Save log into yodee.ir.logging
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)
            # Show success notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Shop information retrieved successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except requests.exceptions.RequestException as e:
            _logger.error(f"Pancake API Request Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to connect to Pancake API: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    ### Bỏ không dùng tạo data fake (ko có thông tin khách hàng không lấy đơn hàng về)
    # def _get_or_create_dummy_partner(self):
    #     """Get or create a dummy partner for Pancake orders"""
    #     dummy_partner = self.env['res.partner'].search([
    #         ('name', '=', 'Pancake Dummy Customer'),
    #     ], limit=1)
    #
    #     if not dummy_partner:
    #         dummy_partner = self.env['res.partner'].sudo().create({
    #             'name': 'Pancake Dummy Customer',
    #             'pancake_customer_id': 'DUMMY',
    #             'customer_rank': 1,
    #             'company_type': 'person',
    #         })
    #
    #     return dummy_partner.id

    def _get_or_create_customer(self, customer_data):
        # có trường hợp không có customer, xem xét không kéo đơn hàng về?
        customer_id = customer_data.get('id') if customer_data else None
        if not customer_id:
            return False
        # Search for existing customer by pancake_customer_id
        partner = self.env['res.partner'].search([
            ('pancake_id', '=', customer_id)
        ], limit=1)

        if partner:
            return partner.id
        else:
            phone = customer_data.get('phone_numbers')[0] if customer_data.get('phone_numbers') else ''
            shop_customer_addresses = customer_data.get('shop_customer_addresses')[0] if customer_data.get('shop_customer_addresses') else ''
            res_partner_data = {
                'pancake_id': customer_id,
                'pancake_customer_id': customer_data.get('customer_id'),
                'name': customer_data.get('name'),
                'email': customer_data.get('emails')[0] if customer_data.get('emails') else '',
                'phone': phone or '',
                'pancake_full_address': shop_customer_addresses.get('full_address', '') if shop_customer_addresses else '',
                'pancake_country_code': shop_customer_addresses.get('country_code','') if shop_customer_addresses else '',
                'pancake_category_id': customer_data.get('tags')[0] if customer_data.get('tags') else '',
                'pancake_assigned_user_id': customer_data.get('assigned_user_id') or '',
                'pancake_gender': customer_data.get('gender') or '',
                'is_sync_pancake': True,
            }
            new_partner = self.env['res.partner'].sudo().create(res_partner_data)
            return new_partner.id

    def _get_product_by_pancake_id(self, product_id, display_id=None):
        """Search for product by Pancake product_id (UUID)"""
        if not product_id:
            return None
        domain  = [('pancake_product_id', '=', product_id)]
        if display_id:
            domain  = ['|',('pancake_product_id', '=', product_id), ('default_code', '=', display_id)]
        # Search product.template by pancake_variant_id
        product_template = self.env['product.template'].search(domain, limit=1)
        # search by barcode
        if not product_template and display_id:
            domain = [('pancake_barcode', '=', display_id)]
            product_template = self.env['product.template'].search(domain, limit=1)
        # Tạo sale order line với product.product (variant)
        if product_template and product_template.product_variant_ids:
            # Return the first product variant
            return product_template.product_variant_ids[0].id

        return None

    def _check_combo_product_by_pancake_id(self, product_id, display_id=None):
        if not product_id:
            return False
        domain  = [('pancake_product_id', '=', product_id)]
        if display_id:
            domain  = ['|',('pancake_product_id', '=', product_id), ('default_code', '=', display_id)]

        # Search product.template by pancake_variant_id
        product_template = self.env['product.template'].search(domain, limit=1)
        if product_template and product_template.combo_product:
            return product_template
        return False


    def _cancel_pancake_order(self, existing_order, reason=None):
        """
        Hủy đơn hàng Odoo tương ứng với 1 đơn Pancake đã bị hủy/xóa (status '6'/'7').
        Nếu đơn đã có phiếu giao hàng hoàn tất (state='done') thì KHÔNG tự động hủy
        (hàng đã xuất kho, hủy sẽ sai lệch tồn kho/công nợ) - chỉ ghi log vào chatter
        của đơn để người dùng tự kiểm tra và xử lý thủ công.
        Trả về True nếu đã hủy, False nếu bị chặn do đã có phiếu giao hàng hoàn tất.
        """
        done_pickings = existing_order.picking_ids.filtered(lambda p: p.state == 'done')
        if done_pickings:
            existing_order.message_post(
                body=_('Đơn hàng bị hủy/xóa trên Pancake%s nhưng đã có phiếu giao hàng hoàn tất (%s) nên hệ '
                       'thống KHÔNG tự động hủy đơn này. Vui lòng kiểm tra và xử lý thủ công.')
                     % ((' (%s)' % reason) if reason else '', ', '.join(done_pickings.mapped('name'))))
            return False

        pickings = existing_order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel'])
        if pickings:
            pickings.sudo().action_cancel()
        wizard = self.env['sale.order.cancel'].sudo().create({'order_id': existing_order.id})
        wizard.action_cancel()
        if reason:
            existing_order.message_post(body=_('Đơn hàng đã được hủy tự động: %s') % reason)
        return True

    def _process_single_order(self, data, pancake_product_surcharge, raise_on_error=False):
        name_order = str(data.get('id'))

        customer_data = data.get('customer')
        partner_id = self._get_or_create_customer(customer_data)
        if not partner_id:
            if raise_on_error:
                raise UserError("Không tìm thấy partner_id")
            return False

        status = str(data.get('status')) if str(data.get('status')) in ORDER_STATUS_MAPPING else None
        if status in ['0']:
            if raise_on_error:
                raise UserError("Status này không cho kéo order")
            return False

        date_pancake = data.get('inserted_at', False)
        date_updated_pancake = data.get('updated_at', False)

        if date_pancake:
            date_pancake = datetime.datetime.fromisoformat(date_pancake)
        if date_updated_pancake:
            date_updated_pancake = datetime.datetime.fromisoformat(date_updated_pancake)

        pancake_source = self.get_data_pancake_source(data.get('account_name'), data.get('order_sources_name'))

        shipping_fee_pancake = data.get('shipping_fee', 0)
        total_discount_pancake = data.get('total_discount', 0)
        surcharge = data.get('surcharge', 0)
        transfer_money = data.get('transfer_money', 0)

        advanced_platform_fee = data.get('advanced_platform_fee', {})
        marketplace_voucher = advanced_platform_fee.get('marketplace_voucher', 0) if advanced_platform_fee else 0

        items = data.get('items', [])
        adj_discount_item = False
        cal_total_discount = {}
        total_price = data.get('total_price', 0) - sum(item.get('variation_info', {}).get('retail_price', 0) for item in items if item.get('variation_info', {}).get('retail_price', 0) * item.get('quantity', 0) - item.get('total_discount', 0) == 0)

        partner_data = data.get('partner', {})
        if not partner_data:
            tracking_id = False
        else:
            tracking_id = (
                partner_data.get('order_number_vtp')
                or partner_data.get('extend_code')
                or False
        )
        for item in items:
            if item.get('quantity', 1) > 0:
                variation_info = item.get('variation_info', {})
                if item.get('components', None) is None:
                    if variation_info.get('retail_price', 0) * item.get('quantity', 0) - item.get('total_discount', 0) > 0:
                        item_price = item.get('quantity', 1) * variation_info.get('retail_price', 0)
                        item_rate = item_price / total_price if total_price else 0
                        cal_total_discount[item.get('id', False)] = {
                            'divide_shipping_fee': round(shipping_fee_pancake * item_rate, 0),
                            'divide_total_discount': round(total_discount_pancake * item_rate, 0),
                            'divide_marketplace_voucher': round(marketplace_voucher * item_rate, 0)
                        }
                        adj_discount_item = item.get('id', False)
                else:
                    for component in item.get('components', []):
                        if component.get('quantity', 1) > 0:
                            if variation_info.get('retail_price', 0) * item.get('quantity', 0) - item.get('total_discount', 0) > 0:
                                component_price = variation_info.get('retail_price', 0) * item.get('quantity', 0)
                                component_rate = component_price / total_price if total_price else 0
                                cal_total_discount[component.get('component_id', False)] = {
                                    'divide_shipping_fee': round(shipping_fee_pancake * component_rate, 0),
                                    'divide_total_discount': round(total_discount_pancake * component_rate, 0),
                                    'divide_marketplace_voucher': round(marketplace_voucher * component_rate, 0)
                                }
                                adj_discount_item = component.get('component_id', False)
        # if len(set(list(cal_total_discount.values()))) == 1:
        cal_total_discount[adj_discount_item] = {
            'divide_shipping_fee': shipping_fee_pancake - sum(cal_total_discount[id]['divide_shipping_fee'] for id in cal_total_discount.keys() if id != adj_discount_item),
            'divide_total_discount': total_discount_pancake - sum(cal_total_discount[id]['divide_total_discount'] for id in cal_total_discount.keys() if id != adj_discount_item),
            'divide_marketplace_voucher': marketplace_voucher - sum(cal_total_discount[id]['divide_marketplace_voucher'] for id in cal_total_discount.keys() if id != adj_discount_item)
        }



        divide_shipping_fee = 0
        divide_total_discount = 0
        divide_marketplace_voucher = 0

        order_lines = []
        combo_product_ids = []
        pancake_missing_info = False
        for item in items:
            item_id = item.get('id', False)
            if item_id in cal_total_discount.keys():
                if shipping_fee_pancake:
                    divide_shipping_fee = cal_total_discount[item_id]['divide_shipping_fee']
                if total_discount_pancake:
                    divide_total_discount = cal_total_discount[item_id]['divide_total_discount']
                if marketplace_voucher:
                    divide_marketplace_voucher = cal_total_discount[item_id]['divide_total_discount']
            product_id = item.get('variation_id')
            variation_info = item.get('variation_info')
            display_id = variation_info.get('display_id') if variation_info else None
            odoo_product_id = self._get_product_by_pancake_id(product_id, display_id)
            quantity = item.get('quantity', 1)
            if quantity > 0 and (not display_id or not product_id):
                pancake_missing_info = True
                continue

            count_combo = 1
            p_combo = self._check_combo_product_by_pancake_id(product_id, display_id)
            if p_combo and p_combo.combo_product:
                combo_product_ids.append(p_combo.id)
                count_combo = len(p_combo.combo_product)

            if not odoo_product_id:
                _logger.warning(f"Product not found for Pancake product_id: {product_id}, skipping item")
                continue

            if not p_combo:
                taxes = self.get_tax_product(odoo_product_id)
                pancake_id = item.get('id')
                variation_info = item.get('variation_info', {})
                pancake_total_discount = item.get('total_discount', 0)
                price_unit = variation_info.get('retail_price', 0)

                pancake_cal = price_unit * quantity - pancake_total_discount
                if variation_info.get('retail_price', 0) * item.get('quantity', 0) - item.get('total_discount', 0) > 0:
                    if divide_shipping_fee:
                        pancake_cal += divide_shipping_fee
                    if divide_total_discount:
                        pancake_cal -= divide_total_discount
                    if divide_marketplace_voucher:
                        pancake_cal += divide_marketplace_voucher

                    new_total_discount = pancake_total_discount + divide_total_discount - divide_marketplace_voucher
                else:
                    new_total_discount = pancake_total_discount
                new_total_discount = self.calculate_price_without_tax(new_total_discount, taxes) / quantity
                price_unit = self.calculate_price_without_tax(pancake_cal, taxes) / quantity
                if new_total_discount:
                    price_unit = price_unit + new_total_discount
                discount_rate = new_total_discount / price_unit if price_unit else 0
                price_unit = round(price_unit, 4)

                order_lines.append((0, 0, {
                    'product_id': odoo_product_id,
                    'tax_id': [(6, 0, taxes.ids)] if taxes else [],
                    'product_uom_qty': quantity,
                    'price_unit': price_unit,
                    'discount': discount_rate * 100,
                    'pancake_total_discount': pancake_total_discount,
                    'name': variation_info.get('name', 'Product'),
                    'pancake_id': str(pancake_id) if pancake_id else '',
                }))
            else:
                # for p_detail in p_combo.combo_product:
                for component in item.get('components'):
                    component_qty = component.get('quantity', 1)
                    component_qty = component_qty * quantity
                    p_detail = p_combo.combo_product.filtered(lambda p: p.default_code == component.get('variation_info').get('id'))
                    p_detail_id = p_detail.product_variant_ids[0].id
                    taxes = self.get_tax_product(p_detail_id)
                    pancake_id = str(item.get('id')) + '_combo_' + str(p_detail.id)
                    variation_info = item.get('variation_info', {})
                    component_id = component.get('component_id', False)
                    if component_id in cal_total_discount.keys():
                        if shipping_fee_pancake:
                            divide_shipping_fee = cal_total_discount[component_id]['divide_shipping_fee']
                        if total_discount_pancake:
                            divide_total_discount = cal_total_discount[component_id]['divide_total_discount']
                        if marketplace_voucher:
                            divide_marketplace_voucher = cal_total_discount[component_id]['divide_marketplace_voucher']
                    pancake_total_discount = item.get('total_discount', 0)
                    price_unit = variation_info.get('retail_price', 0)

                    pancake_cal = price_unit * quantity - pancake_total_discount
                    pancake_cal = pancake_cal / count_combo
                    combo_pancake_total_discount = pancake_total_discount / count_combo
                    if variation_info.get('retail_price', 0) * item.get('quantity', 0) - item.get('total_discount', 0) > 0:
                        if divide_shipping_fee:
                            pancake_cal += divide_shipping_fee
                        if divide_total_discount:
                            pancake_cal -= divide_total_discount
                        if divide_marketplace_voucher:
                            pancake_cal += divide_marketplace_voucher

                        new_total_discount = combo_pancake_total_discount + divide_total_discount - divide_marketplace_voucher
                    else:
                        new_total_discount = combo_pancake_total_discount
                    new_total_discount = self.calculate_price_without_tax(new_total_discount, taxes) / component_qty
                    price_unit = self.calculate_price_without_tax(pancake_cal, taxes) / component_qty
                    if new_total_discount:
                        price_unit = price_unit + new_total_discount
                    discount_rate = new_total_discount / price_unit if price_unit else 0
                    price_unit = round(price_unit, 4)

                    order_lines.append((0, 0, {
                        'product_id': p_detail_id,
                        'tax_id': [(6, 0, taxes.ids)] if taxes else [],
                        'product_uom_qty': component_qty,
                        'price_unit': price_unit,
                        'discount': discount_rate * 100,
                        'pancake_total_discount': combo_pancake_total_discount,
                        'name': variation_info.get('name', 'Product'),
                        'pancake_id': str(pancake_id) if pancake_id else '',
                    }))

        affiliate_commission = advanced_platform_fee.get('affiliate_commission', 0) if advanced_platform_fee else 0
        diff_shipping_fee = advanced_platform_fee.get('diff_shipping_fee', 0) if advanced_platform_fee else 0
        payment_fee = advanced_platform_fee.get('payment_fee', 0) if advanced_platform_fee else 0
        platform_commission = advanced_platform_fee.get('platform_commission', 0) if advanced_platform_fee else 0
        seller_transaction_fee = advanced_platform_fee.get('seller_transaction_fee', 0) if advanced_platform_fee else 0
        service_fee = advanced_platform_fee.get('service_fee', 0) if advanced_platform_fee else 0
        sfp_service_fee = advanced_platform_fee.get('sfp_service_fee', 0) if advanced_platform_fee else 0
        total_fee_marketplace = data.get('fee_marketplace', 0)

        shipping_address = data.get('shipping_address', {})
        province_id = self.env['pancake.provinces'].sudo().search(
            [('api_province_id', '=', shipping_address.get('province_id'))])
        district_id = self.env['pancake.districts'].sudo().search(
            [('api_district_id', '=', shipping_address.get('district_id'))])
        communes_id = self.env['pancake.communes'].sudo().search(
            [('api_communes_id', '=', shipping_address.get('commune_id'))])
        shipping_full_name = shipping_address.get('full_name', '')
        username = customer_data.get('username', '')
        if shipping_full_name and username and '*' in shipping_full_name:
            shipping_full_name = username

        shipping_phone = shipping_address.get('phone_number', '')
        shipping_full_address = shipping_address.get('full_address', '')
        shipping_province_id = province_id.id if province_id else False
        shipping_district_id = district_id.id if district_id else False
        shipping_communes_id = communes_id.id if communes_id else False

        if surcharge > 0 and pancake_product_surcharge:
            order_lines.append((0, 0, {
                'product_id': pancake_product_surcharge.id,
                'tax_id': [],
                'product_uom_qty': 1,
                'price_unit': surcharge,
                'name': pancake_product_surcharge.name,
            }))

        order_data = {
            'name': name_order,
            'date_pancake': date_pancake,
            'date_updated_pancake': date_updated_pancake,
            'pancake_order_id': name_order,
            'pancake_order_json': data,
            'pancake_source_id': pancake_source.id if pancake_source else False,
            'partner_id': partner_id,
            'order_line': order_lines,
            'pancake_status': status,
            'affiliate_commission': affiliate_commission,
            'diff_shipping_fee': diff_shipping_fee,
            'marketplace_voucher': marketplace_voucher,
            'payment_fee': payment_fee,
            'platform_commission': platform_commission,
            'seller_transaction_fee': seller_transaction_fee,
            'service_fee': service_fee,
            'sfp_service_fee': sfp_service_fee,
            'total_fee_marketplace': total_fee_marketplace,
            'shipping_full_name': shipping_full_name,
            'shipping_phone': shipping_phone,
            'shipping_full_address': shipping_full_address,
            'shipping_province_id': shipping_province_id,
            'shipping_district_id': shipping_district_id,
            'shipping_communes_id': shipping_communes_id,
            'total_discount_pancake': total_discount_pancake,
            'transfer_money': transfer_money,
            'order_receiver': shipping_full_name,
            'pancake_missing_info': pancake_missing_info,
            'tracking_id': tracking_id
        }
        if combo_product_ids:
            order_data['combo_product_ids'] = [(6, 0, combo_product_ids)]

        existing_order = self.env['sale.order'].search(
            [('pancake_order_id', '=', str(data.get('id')))], limit=1)
        if existing_order:
            if existing_order.mark_done_cron:
                return True
            order_data.pop('order_line')
            existing_order.sudo().write(order_data)
            for new_pancake_line in order_lines:
                e_line = existing_order.order_line.filtered(
                    lambda l: l.pancake_id == new_pancake_line[2]['pancake_id'])
                if e_line:
                    existing_order.sudo().locked = False
                    e_line.sudo().write({
                        'price_unit': new_pancake_line[2]['price_unit'],
                        'discount': new_pancake_line[2].get('discount', 0),
                        'pancake_total_discount': new_pancake_line[2]['pancake_total_discount']
                    })
                    if e_line.product_uom_qty != new_pancake_line[2]['product_uom_qty']:
                        e_line.sudo().write({
                            'product_uom_qty': new_pancake_line[2]['product_uom_qty']
                        })

            line_surcharge = existing_order.order_line.filtered(
                lambda l: l.product_id.id == pancake_product_surcharge.id)
            if line_surcharge:
                if line_surcharge[0].price_unit != surcharge:
                    line_surcharge.sudo().write({'price_unit': surcharge})

            line_combo = existing_order.order_line.filtered(
                lambda l: l.product_id.combo_product and l.pancake_id)
            for line in line_combo:
                line.sudo().write({'product_uom_qty': 0, 'pancake_total_discount': 0, 'price_unit': 0})

            if existing_order.pancake_status != status:
                existing_order.sudo().write({'pancake_status': status})

            if status in ['6', '7'] and existing_order.state in ['draft', 'sent', 'sale']:
                self._cancel_pancake_order(existing_order)
                return True

            pickings = existing_order.picking_ids
            all_done = all(p.state == 'done' for p in pickings)
            if all_done and pickings:
                existing_order.sudo().write({
                    'internal_note': f"Đơn hàng đã giao lúc {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
                })

            existing_lines_map = {line.pancake_id: line for line in existing_order.order_line}
            for line_data in order_lines:
                if 'display_type' not in line_data[2]:
                    pancake_id = line_data[2].get('pancake_id')
                    product_id = line_data[2].get('product_id')
                    price_unit = line_data[2].get('price_unit')
                    if pancake_id and pancake_id in existing_lines_map:
                        existing_line = existing_lines_map[pancake_id]
                        line_vals = {}
                        if line_data[2].get('price_unit') not in (None, ''):
                            line_vals['price_unit'] = line_data[2]['price_unit']
                        if line_data[2].get('tax_id'):
                            line_vals['tax_id'] = line_data[2]['tax_id']
                        if line_data[2].get('pancake_total_discount') not in (None, ''):
                            line_vals['pancake_total_discount'] = line_data[2]['pancake_total_discount']
                        if line_data[2].get('name'):
                            line_vals['name'] = line_data[2]['name']
                        if line_vals:
                            existing_line.sudo().write(line_vals)
                    elif pancake_id and pancake_id not in existing_lines_map:
                        existing_order.sudo().write({'order_line': [(0, 0, line_data[2])]})
                    else:
                        line_check = existing_order.order_line.filtered(
                            lambda l: l.product_id.id == product_id and not l.pancake_id)
                        if line_check:
                            if line_check[0].price_unit != price_unit:
                                line_check[0].sudo().write({'price_unit': price_unit})
                        else:
                            existing_order.sudo().write({'order_line': [(0, 0, line_data[2])]})
        else:
            order = self.env['sale.order'].sudo().create(order_data)
            if order.pancake_status not in ['6', '7']:
                if order.state in ['draft', 'sent']:
                    order.sudo().action_confirm()
            else:
                if order.state != 'cancel':
                    order.sudo().action_cancel()

        return True

    # chưa tìm đc param search đơn hàng theo trạng thái, sẽ
    def get_order_list(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + '/shops/' + pancake_connector.shop_id + '/orders?api_key=' + pancake_connector.pancake_api_key

        page_number = pancake_connector.order_page
        page_size = pancake_connector.order_page_size

        has_more = True

        date_from = pancake_connector.order_date_from
        date_to = pancake_connector.order_date_to
        duration = pancake_connector.order_duration
        order_break_day = pancake_connector.order_break_day


        # Trạng thái đơn hàng cần lấy (Trừ trạng thái 0 - mơí tạo)
        filter_status = [17, 11, 12, 13, 20, 1, 8, 9, 2, 3, 16, 4, 15, 5, 6, 7]

        order_time = pancake_connector.order_time
        now = datetime.datetime.now()

        # Xử lý thời gian bắt đầu và kết thúc
        if not date_from and not date_to:
            date_from = now
            date_to = now + datetime.timedelta(minutes=duration)
        elif not date_from:
            date_from = date_to
            date_to = date_to + datetime.timedelta(minutes=duration)
        elif not date_to:
            date_to = date_from + datetime.timedelta(minutes=duration)
        if date_from and date_from > now:
            date_from = now
        if not date_to or date_to < date_from:
                date_to = date_from + datetime.timedelta(minutes=duration)

        # Gán lại vào object
        self.env.cr.execute(f"""
                            UPDATE {pancake_connector._table}
                            SET order_date_from = %s, order_date_to = %s
                            WHERE id = %s
                        """, (date_from, date_to, pancake_connector.id))
        # Bỏ qua 0
        timeout_seconds = pancake_connector.timeout_minutes_order * 60  # thời gian tối đa chạy cron
        start_time = datetime.datetime.now()
        while has_more:
            # Kiểm tra timeout ---
            elapsed_seconds = (datetime.datetime.now() - start_time).total_seconds()
            if elapsed_seconds > timeout_seconds:
                _logger.info(f"Cron get_order_list đã chạy quá {elapsed_seconds}s, sẽ dừng và tiếp tục lần sau.")
                break
            # lọc theo trạng thái
            params = {
                'page_number': page_number,
                'page_size': page_size,
            }
            if order_time:
                if pancake_connector.order_date_from:
                    params['startDateTime'] = int(pancake_connector.order_date_from.timestamp())
                if pancake_connector.order_date_to and pancake_connector.order_date_to < datetime.datetime.now():
                    params['endDateTime'] = int(pancake_connector.order_date_to.timestamp())
                if params.get('startDateTime') or params.get('endDateTime'):
                    params['updateStatus'] = 'updated_at'
                if filter_status:
                    params['filter_status[]'] = [int(s) for s in filter_status]
            try:
                print('____________________')

                response = requests.request("GET", url, params=params)
                response.raise_for_status()
                datas = response.json()
                orders = datas.get('data', [])
                print('orders:', len(orders))
                # Sản phẩm phụ thu
                pancake_product_surcharge = self.env.ref('advanced_sync_pancake.pancake_product_surcharge').product_variant_id[0]

                for data in orders:
                    name_order = str(data.get('id'))
                    date_pancake_str = data.get('inserted_at', False)
                    now = datetime.datetime.now()
                    time_check = now - datetime.timedelta(days=order_break_day)
                    if date_pancake_str:
                        date_pancake_dt = datetime.datetime.fromisoformat(date_pancake_str)
                        if date_pancake_dt < time_check:
                            IrLogging = self.env['ir.logging']
                            date_pancake_text = date_pancake_dt.strftime('%Y-%m-%d %H:%M:%S')
                            message = f"Đơn hàng Pancake ID {name_order} có ngày tạo {date_pancake_text} quá cũ, không lấy về."
                            IrLogging.sudo().create({'name': 'get_order_list_pancake',
                                                     'type': 'server',
                                                     'message': message,
                                                     'path': name_order,
                                                     'func': date_pancake_text,
                                                     'line': 1})
                            continue
                    self._process_single_order(data, pancake_product_surcharge)

                # add logging
                logging = self.env['yodee.ir.logging'].sudo()
                logging.log_outgoing_request(response)

                # --- kiểm tra nếu còn trang kế tiếp ---
                if len(orders) >= page_size:
                    print('page_number:', page_number)
                    # Còn trang tiếp theo
                    page_number += 1
                    # pancake_connector.order_page = page_number

                    # Dùng f-string cho tên bảng (vì %s không dùng được cho table name)
                    self.env.cr.execute(f"""
                                UPDATE {pancake_connector._table}
                                SET order_page = %s
                                WHERE id = %s
                            """, (page_number, pancake_connector.id))
                    has_more = True
                else:
                    has_more = False
                    now = datetime.datetime.now()
                    if pancake_connector.order_date_to <= now:
                        new_date_from = pancake_connector.order_date_to
                        new_date_to = pancake_connector.order_date_to + datetime.timedelta(minutes=duration)
                    else:
                        # Nếu vượt quá hiện tại call lùi lại quá khứ trước thời điểm hiện tại
                        new_date_from = now - datetime.timedelta(minutes=duration)
                        new_date_to = now
                    self.env.cr.execute(f"""
                                UPDATE {pancake_connector._table}
                                SET order_date_from = %s,
                                    order_date_to   = %s,
                                    order_page      = 1
                                WHERE id = %s
                            """, (new_date_from, new_date_to, pancake_connector.id))
            except Exception as e:
                _logger.error(f"Unexpected Error: {str(e)}")

    def get_product_list(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + '/shops/' + pancake_connector.shop_id + '/products/variations?api_key=' + pancake_connector.pancake_api_key

        page_number = pancake_connector.product_page
        page_size = pancake_connector.product_page_size

        has_more = True

        date_from = pancake_connector.product_date_from
        date_to = pancake_connector.product_date_to
        duration = pancake_connector.product_duration
        product_time = pancake_connector.product_time
        now = datetime.datetime.now()

        # Xử lý thời gian bắt đầu và kết thúc
        if not date_from and not date_to:
            date_from = now
            date_to = now + datetime.timedelta(minutes=duration)
        elif not date_from:
            date_from = date_to
            date_to = date_to + datetime.timedelta(minutes=duration)
        elif not date_to:
            date_to = date_from + datetime.timedelta(minutes=duration)
        if date_from and date_from > now:
            date_from = now
        if not date_to or date_to < date_from:
            date_to = date_from + datetime.timedelta(minutes=duration)

        # Gán lại vào object
        pancake_connector.product_date_from = date_from
        pancake_connector.product_date_to = date_to

        timeout_seconds = pancake_connector.timeout_minutes_product * 60  # thời gian tối đa chạy cron
        start_time = datetime.datetime.now()
        while has_more:
            # Kiểm tra timeout ---
            elapsed_seconds = (datetime.datetime.now() - start_time).total_seconds()
            if elapsed_seconds > timeout_seconds:
                _logger.info(f"Cron đã chạy quá {elapsed_seconds}s, sẽ dừng và tiếp tục lần sau.")
                break
            params = {
                'page_number': page_number,
                'page_size': page_size,
            }
            if product_time:
                if pancake_connector.product_date_from:
                    params['start_time_update'] = int(pancake_connector.product_date_from.timestamp())
                if pancake_connector.product_date_to and pancake_connector.product_date_to < datetime.datetime.now():
                    params['end_time_update'] = int(pancake_connector.product_date_to.timestamp())
            try:
                response = requests.request("GET", url, params=params)
                response.raise_for_status()
                datas = response.json()
                products = datas.get('data', [])
                print('products:', len(products))
                for data in products:
                    product_template_id = str(data.get('product_id'))
                    pancake_product_template_id = self.env['pancake.product.template'].search([('pancake_product_template_id', '=', product_template_id)], limit=1)
                    if not pancake_product_template_id:
                        # create pancake product template
                        pancake_product_template_id = self.env['pancake.product.template'].sudo().create({
                            'name': data.get('product')['name'],
                            'description': data.get('product')['note_product'],
                            'default_code': data.get('product')['display_id'],
                            'pancake_product_template_id': product_template_id,
                            'product_template_json': json.dumps(data.get('product')),
                        })
                    else:
                        pancake_product_template_id.sudo().write({
                            'name': data.get('product')['name'],
                            'product_template_json': json.dumps(data.get('product')),
                        })
                    default_code =  data.get('display_id', '')
                    existing_product = self.env['product.template'].search(['|', ('pancake_product_id', '=', str(data.get('id'))), ('default_code','=',default_code)])


                    attr_values = []
                    product_info = data.get('product', {})
                    # Lấy giá trị thuộc tính sản phẩm điền vào tên sản phẩm
                    attributes = data.get('fields', [])
                    for attr in attributes:
                        att_name = attr.get('name', [])
                        value = attr.get('value', [])
                        if value and att_name:
                            attr_values.append(str(att_name)+': '+str(value))  # lấy giá trị thuộc tính thực tế

                    if attr_values:
                        full_name = f"{data.get('product')['name']} ({', '.join(attr_values)})"
                    else:
                        full_name = data.get('product')['name']

                    # Lấy mã thương hiêu (brand) nếu có
                    brands = product_info.get('supplier_product_ids', {})
                    pancake_brands = []
                    for b in brands:
                        branch = self.env['pancake.branch'].sudo().search([
                            ('pancake_supplier_id', '=', str(b))
                        ], limit=1)
                        if branch:
                            pancake_brands.append(branch.id)

                    product_data = {
                        'name': full_name,
                        'pancake_product_id': str(data.get('id')),
                        'pancake_barcode': data.get('barcode', ''),
                        'default_code': data.get('display_id', ''),
                        'pancake_product_template_id': pancake_product_template_id.id,
                        'description' : data.get('product')['note_product'],
                        'pancake_order_json': data,
                    }
                    if pancake_brands:
                        product_data['pancake_brand_ids'] = [(6, 0, pancake_brands)]
                    # ================= COMBO PRODUCT ở đây nha =================

                    combo_ids = []

                    for combo in data.get('composite_products', []):
                        component = combo.get('component', {})
                        if not component:
                            continue

                        child_display_id = component.get('display_id')
                        if not child_display_id:
                            continue

                        child_product = self.env['product.template'].search([
                            ('default_code', '=', child_display_id)
                        ], limit=1)
                        if child_product:
                            combo_ids.append(child_product.id)

                    # =================================================
                    if existing_product:
                        vals = product_data
                        if combo_ids:
                            vals['combo_product'] = [(6, 0, combo_ids)]
                        existing_product.sudo().write(vals)
                    else:
                        product_data['is_storable'] = True
                        if combo_ids:
                            product_data['combo_product'] = [(6, 0, combo_ids)]
                        self.env['product.template'].sudo().create(product_data)
                # add logging
                logging = self.env['yodee.ir.logging'].sudo()
                logging.log_outgoing_request(response)

                # --- kiểm tra nếu còn trang kế tiếp ---
                if len(products) >= page_size:
                    # Còn trang tiếp theo
                    page_number += 1

                    #Dùng f-string cho tên bảng (vì %s không dùng được cho table name)
                    self.env.cr.execute(f"""
                        UPDATE {pancake_connector._table}
                        SET product_page = %s
                        WHERE id = %s
                    """, (page_number, pancake_connector.id))
                    has_more = True

                else:
                    has_more = False

                    now = datetime.datetime.now()
                    if pancake_connector.product_date_to <= now:
                        new_date_from = pancake_connector.product_date_to
                        new_date_to = pancake_connector.product_date_to + datetime.timedelta(minutes=duration)
                    else:
                        # Nếu vượt quá hiện tại call lùi lại quá khứ trước thời điểm hiện tại
                        new_date_from = now - datetime.timedelta(minutes=duration)
                        new_date_to = now
                    self.env.cr.execute(f"""
                                        UPDATE {pancake_connector._table}
                                        SET product_date_from = %s,
                                            product_date_to   = %s,
                                            product_page      = 1
                                        WHERE id = %s
                                    """, (new_date_from, new_date_to, pancake_connector.id))
            except Exception as e:
                _logger.error(f"Unexpected Error: {str(e)}")

    def get_stock_warehouse(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = pancake_connector.pancake_url + '/shops/' + pancake_connector.shop_id + '/warehouses?api_key=' + pancake_connector.pancake_api_key
        try:
            response = requests.request("GET", url)
            response.raise_for_status()
            datas = response.json()
            warehouses = datas.get('data', [])
            for data in warehouses:
                existing_warehouse = self.env['pancake.warehouse'].search([('pancake_warehouse_id', '=', str(data.get('id')))])
                if existing_warehouse:
                    continue  # Skip existing warehouses

                warehouse_data = {
                    'name': data.get('name'),
                    'pancake_warehouse_id': str(data.get('id')),
                    'warehouse_json': json.dumps(data),
                }
                self.env['pancake.warehouse'].sudo().create(warehouse_data)

            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")

    def get_data_pancake_source(self, account_name, source_name):
        if not source_name:
            return False

        full_name = (
            f"{source_name} / {account_name}"
            if account_name
            else source_name
        )

        PancakeSource = self.env['pancake.order.source'].sudo()

        pancake_source = PancakeSource.search([
            ('name', '=', full_name)
        ], limit=1)

        # Mapping partner theo source
        partner_id = self._get_partner_by_order_source(source_name)

        # Nếu source đã tồn tại
        if pancake_source:

            # Chưa có default customer thì cập nhật
            if not pancake_source.default_customer and partner_id:
                pancake_source.default_customer = partner_id

            return pancake_source

        # Nếu chưa có source thì tạo mới
        vals = {
            'name': full_name,
        }

        # Chỉ gán default customer nếu có mapping
        if partner_id:
            vals['default_customer'] = partner_id

        new_pancake_source = PancakeSource.create(vals)

        return new_pancake_source

    def get_tax_product(self, product_id):
        product_template = self.env['product.product'].search([
            ('id', '=', product_id)
        ], limit=1)
        if product_template.taxes_id:
            return product_template.taxes_id    # Trả về list thuế
        else:
            return False

    def get_tax_multiplayer(self,taxes):
        total_percent = sum(tax.amount for tax in taxes)
        return 1 + (total_percent / 100.0)

    def calculate_price_without_tax(self, price_with_tax, taxes):
        if not taxes:
            return price_with_tax
        multiplier = self.get_tax_multiplayer(taxes)
        return price_with_tax / multiplier

    def action_sync_stock(self):
        for record in self:
            # pencake_shop_id = 1328343891
            pancake_connector = record.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
            if not pancake_connector:
                _logger.error("Chưa cấu hình Pancake Connector")
                return

            url = f"https://pos.pages.fm/api/v1/shops/{pancake_connector.shop_id}/products/variations"
            params = {
                'api_key': pancake_connector.pancake_api_key,
                'page_number': record.page_number,
                'page_size': record.page_size,
            }
            if record.sync_product_date_from:
                params['date_from'] = fields.Datetime.to_string(record.sync_product_date_from)
            if record.sync_product_date_to:
                params['date_to'] = fields.Datetime.to_string(record.sync_product_date_to)
            try:
                # _logger.info(f"[SYNC STOCK] Gọi API: {url} | Params: {params}")
                response = requests.get(url, params=params)
                response.raise_for_status()
                datas = response.json().get('data', [])

            except Exception as e:
                # _logger.error(f"Lỗi khi gọi API Pancake: {str(e)}")
                return

            if not datas:
                _logger.info("Hết dữ liệu, đánh dấu sync_stock_done=True")
                record.sync_stock_done = True
                return

            for item in datas:
                product_sku = item.get('display_id')
                variations_warehouses = item.get('variations_warehouses', [])

                product = record.env['product.product'].search([('default_code', '=', product_sku)], limit=1)
                if not product:
                    # _logger.warning(f"Không tìm thấy sản phẩm {product_sku}")
                    continue

                for vwh in variations_warehouses:
                    pancake_wh_id = vwh.get('warehouse_id')
                    remain_qty = vwh.get('remain_quantity', 0)

                    location = self.env['stock.location'].search(
                        [('pancake_id', '=', pancake_wh_id)], limit=1)
                    # )
                    # if not warehouse_mapping or not warehouse_mapping.odoo_pencake_warehouse_id:
                    #     _logger.warning(f"Không tìm thấy mapping kho Pancake {pancake_wh_id}")
                    #     continue
                    #
                    # location = warehouse_mapping.odoo_pencake_warehouse_id.lot_stock_id
                    quant = record.env['stock.quant'].sudo().search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', location.id)
                    ], limit=1)
                    if quant:
                        quant.sudo().write({'quantity': remain_qty})
                    #Nếu có thì cập nhật , nếu không có code hiện tại k cho tự thêm
                    # else:
                    #     record.env['stock.quant'].sudo().create({
                    #         'product_id': product.id,
                    #         'location_id': location.id,
                    #         'quantity': remain_qty,
                    #     })

            record.page_number += 1
            record.last_sync_time = fields.Datetime.now()

    def sync_brands(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/supplier"
        params = {'api_key': pancake_connector.pancake_api_key}

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json().get('data', [])

        for s in data:
            supplier_id = str(s.get('id'))

            # Todo ko cần đồng bộ partner nữa
            # partner_vals = {
            #     'name': s.get('name'),
            #     'phone': s.get('phone_number'),
            #     'street': s.get('address'),
            #     'supplier_rank': 1,  # Đánh dấu là vendor trong Odoo
            #     'pancake_supplier_id': supplier_id,
            # }
            #
            # partner = self.env['res.partner'].sudo().search([
            #     ('pancake_supplier_id', '=', supplier_id)
            # ], limit=1)
            #
            # if partner:
            #     partner.write(partner_vals)
            # else:
            #     self.env['res.partner'].sudo().create(partner_vals)

            branch_vals = {
                'pancake_supplier_id': supplier_id,
                'name': s.get('name'),
                'pancake_order_json': s,
            }
            branch = self.env['pancake.branch'].sudo().search([
                ('pancake_supplier_id', '=', supplier_id)
            ], limit=1)
            if branch:
                branch.write(branch_vals)
            else:
                self.env['pancake.branch'].sudo().create(branch_vals)

    def sync_employees(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/users"
        params = {'api_key': pancake_connector.pancake_api_key}

        respond = requests.get(url, params=params)
        respond.raise_for_status()
        data = respond.json().get('data', [])

        for s in data:
            user = s.get('user',{})
            name = user.get('name')
            email = user.get('email') or ''
            if not name or name == "API_CONNECTION":
                continue

            employee_id = str(s.get('id'))

            employee_vals = {
                'name': name,
                'phone': s.get('phone_number') or '',
                'work_email': email,
                'pancake_employee_id': employee_id,
            }

            employee = self.env['hr.employee'].sudo().search([
                '|',
                ('pancake_employee_id', '=', employee_id),
                ('work_email', '=', email),
            ], limit=1)

            if employee:
                employee.write(employee_vals)
            else:
                self.env['hr.employee'].sudo().create(employee_vals)

        # Ghi thêm logging vào odoo
        logging = self.env['yodee.ir.logging'].sudo()
        logging.log_outgoing_request(respond)

    def sync_warehouse(self):
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/warehouses"
        params = {'api_key': pancake_connector.pancake_api_key}

        respond = requests.get(url, params=params)
        respond.raise_for_status()
        data = respond.json().get('data', [])

        for warehouse in data:
            name = warehouse.get('name') or ''
            pancake_warehouse_id = warehouse.get('id') or ''
            pancake_custom_id = warehouse.get('custom_id') or ''
            phone_number = warehouse.get('phone_number') or ''
            address = warehouse.get('address') or ''
            full_address = warehouse.get('full_address') or ''
            api_district_id = warehouse.get('district_id') or ''
            api_province_id = warehouse.get('province_id') or ''
            api_communes_id = warehouse.get('commune_id') or ''
            api_country_code = warehouse.get('country_code') or ''

            warehouse_data = {
                'name': name,
                'pancake_warehouse_id': pancake_warehouse_id,
                'pancake_custom_id': pancake_custom_id,
                'phone_number': phone_number,
                'address': address,
                'full_address': full_address,
                'api_district_id': api_district_id,
                'api_province_id': api_province_id,
                'api_communes_id': api_communes_id,
                'api_country_code': api_country_code,
                'warehouse_json': warehouse,
            }

            warehouse = self.env['pancake.warehouse'].sudo().search([
                ('pancake_warehouse_id', '=', pancake_warehouse_id)], limit=1)

            if warehouse:
                warehouse.write(warehouse_data)
            else:
                self.env['pancake.warehouse'].sudo().create(warehouse_data)

        # Ghi thêm logging vào odoo
        logging = self.env['yodee.ir.logging'].sudo()
        logging.log_outgoing_request(respond)

    def get_order_by_id(self, order_id):
        """
        Lấy chi tiết 1 đơn hàng từ Pancake và đồng bộ vào Odoo.
        Trả về True nếu lấy và xử lý thành công, False nếu KHÔNG lấy được đơn từ Pancake
        (đơn không tồn tại/đã bị xóa hoàn toàn trên Pancake, hoặc lỗi gọi API).
        """
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1')
        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/orders/{order_id}?api_key={pancake_connector.pancake_api_key}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            order = data.get('data')

            if not order:
                _logger.warning(f"Không tìm thấy order {order_id}")
                return False

            pancake_product_surcharge = self.env.ref('advanced_sync_pancake.pancake_product_surcharge').product_variant_id[0]
            self._process_single_order(order, pancake_product_surcharge, raise_on_error=True)
            return True

        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Lỗi khi lấy order {order_id}: {str(e)}")
            return False

    def action_sync_pancake_order(self):
        for rec in self:
            if rec.pancake_order_id:
                rec.get_order_by_id(rec.pancake_order_id)

    def _cron_process_pancake_order_webhook(self, limit=100):
        """
        Xử lý các webhook đơn hàng Pancake đang ở trạng thái 'pending', gom theo từng đơn
        (pancake_order_id) để việc bỏ qua webhook cũ được tính riêng cho từng đơn hàng:
        - Nếu đơn đã có 1 webhook 'done'/'order_deleted' với create_date mới hơn thì các
          webhook 'pending' cũ hơn của CHÍNH đơn đó bị coi là cũ -> đánh dấu 'skipped'.
        - Với các webhook 'pending' còn lại của 1 đơn: gọi get_order_by_id() 1 lần (vì hàm
          này luôn lấy dữ liệu mới nhất từ Pancake và tự xử lý hủy đơn khi status='6'/'7'
          thông qua _process_single_order):
            + Lấy được đơn -> đánh dấu webhook 'done', hoặc 'order_deleted' nếu trạng thái
              Pancake mới nhất là '7' (Đã xóa).
            + KHÔNG lấy được đơn (order_id không còn tồn tại/đã bị xóa hoàn toàn trên
              Pancake) và trạng thái webhook mới nhất là '7': coi như đơn chắc chắn đã bị
              xóa -> tự hủy sale.order tương ứng trong Odoo (qua _cancel_pancake_order) và
              ghi log, vì sẽ không còn cơ hội nào khác để lấy lại dữ liệu đơn này từ Pancake.
            + KHÔNG lấy được đơn nhưng trạng thái không phải '7': đánh dấu webhook 'error'
              để có thể retry thủ công sau.
        """
        pancake_connector = self.env.ref('advanced_sync_pancake.pancake_connector_1', raise_if_not_found=False)
        if not pancake_connector:
            return

        Webhook = self.env['pancake.order.webhook'].sudo()
        pending_webhooks = Webhook.search(["|", ("state", "=", "pending"), "&", ("state", "=", "error"), ("pancake_status", "!=", "0")], order='create_date asc', limit=limit)

        webhooks_by_order = {}
        for webhook in pending_webhooks:
            webhooks_by_order.setdefault(webhook.pancake_order_id, Webhook)
            webhooks_by_order[webhook.pancake_order_id] |= webhook

        for order_id, webhooks in webhooks_by_order.items():
            last_done = Webhook.search([
                ('pancake_order_id', '=', order_id),
                ('state', 'in', ('done', 'order_deleted')),
            ], order='create_date desc', limit=1)

            # Bỏ qua các webhook cũ hơn webhook đã xử lý thành công gần nhất của CÙNG đơn hàng này
            if last_done:
                stale_webhooks = webhooks.filtered(lambda w: w.create_date <= last_done.create_date)
                if stale_webhooks:
                    stale_webhooks.write({'state': 'skipped', 'processed_date': fields.Datetime.now()})
                    webhooks -= stale_webhooks

            if not webhooks:
                continue

            latest_webhook = webhooks.sorted(key=lambda w: w.create_date)[-1]
            is_deleted_status = latest_webhook.pancake_status == '7'

            try:
                fetched = pancake_connector.get_order_by_id(order_id)
                if fetched:
                    webhooks.write({
                        'state': 'order_deleted' if is_deleted_status else 'done',
                        'processed_date': fields.Datetime.now(),
                    })
                elif is_deleted_status:
                    # Không lấy được đơn từ Pancake (đơn đã bị xóa hoàn toàn) -> tự hủy
                    # sale.order tương ứng trong Odoo thay vì bỏ qua.
                    existing_order = self.env['sale.order'].sudo().search(
                        [('pancake_order_id', '=', order_id)], limit=1)
                    if existing_order:
                        self._cancel_pancake_order(
                            existing_order,
                            reason=_('không lấy được đơn từ Pancake, đơn đã bị xóa hoàn toàn trên Pancake'))
                    webhooks.write({'state': 'order_deleted', 'processed_date': fields.Datetime.now()})
                else:
                    webhooks.write({
                        'state': 'error',
                        'error_message': f'Không lấy được dữ liệu đơn hàng từ Pancake (order_id={order_id})',
                        'processed_date': fields.Datetime.now(),
                    })
            except Exception as e:
                _logger.error(f"Lỗi khi xử lý webhook order {order_id}: {str(e)}")
                webhooks.write({
                    'state': 'error',
                    'error_message': str(e),
                    'processed_date': fields.Datetime.now(),
                })
            self.env.cr.commit()

    def _get_partner_by_order_source(self, order_source_name):
        source_mapping = {
            'facebook': 'SAN_FACEBOOK',
            'tiki': 'SAN_TIKI',
            'lazada': 'SAN_LAZADA',
            'shopee': 'SAN_SHOPEE',
            'tiktok': 'SAN_TIKTOK',
            'event': 'SAN_EVENT',
            'instagram': 'SAN_INSTAGRAM',
        }


        if not order_source_name:
            return False

        order_source_name = order_source_name.lower()

        # Nhóm sàn
        for key, customer_code in source_mapping.items():
            if key in order_source_name:
                partner = self.env['res.partner'].sudo().search([
                    ('customer_code', '=', customer_code)
                ], limit=1)

                if partner:
                    return partner.id

        # Nhóm retail
        if order_source_name in ['showroom','zalo','website','staff']:
            partner = self.env['res.partner'].sudo().search([
                ('customer_code', '=', 'OTHER_RETAIL')
            ], limit=1)

            if partner:
                return partner.id

        return False