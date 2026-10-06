from odoo import fields, models, api, _
import requests
import json
from odoo import models
from odoo.exceptions import UserError


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    contact_address_inline = fields.Char(tracking=False)
    street = fields.Char(tracking=True)
    pancake_customer_id = fields.Char('Customer ID', copy=False)
    pancake_full_address = fields.Char('Địa chỉ', tracking=True)
    pancake_country_code = fields.Char('Mã quốc gia')
    pancake_country_state_code = fields.Many2one('pancake.provinces', string='Mã tỉnh/thành phố', ondelete='set null')
    pancake_country_ward_code = fields.Many2one('pancake.communes', string='Mã phường/xã', ondelete='set null')
    pancake_category_id = fields.Char('Nhãn phân loại')
    pancake_assigned_user_id = fields.Char('Nhân viên sale phụ trách')
    pancake_gender = fields.Char('Giới tính')
    pancake_id = fields.Char('Pancake id', copy=False)
    pancake_address_id = fields.Char('Pancake address id', copy=False)
    pancake_note = fields.Text('Note')
    pancake_supplier_id = fields.Char('Pancake Supplier ID')
    pancake_order_json = fields.Json(string='Dữ liệu đơn hàng Pancake', copy=False)
    pancake_order_json_text = fields.Text(string="Pancake Order (Text)", compute="_compute_json_text")
    is_sync_pancake = fields.Boolean(default=False, copy=False)
    province_name = fields.Char(compute='_compute_location_names')
    ward_name = fields.Char(compute='_compute_location_names')

    sale_area_id = fields.Many2one('sale.area', string='Sale Area')

    @api.depends("pancake_order_json")
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.pancake_order_json_text = ""
                if rec.pancake_order_json:
                    rec.pancake_order_json_text = json.dumps(rec.pancake_order_json, indent=4, ensure_ascii=False)
            except Exception:
                rec.pancake_order_json_text = ""

    @api.depends('pancake_country_state_code', 'pancake_country_ward_code')
    def _compute_location_names(self):
        for record in self:
            record.province_name = record.pancake_country_state_code.name or ''
            record.ward_name = record.pancake_country_ward_code.name or ''


    def pancake_sync_customer(self):
        for rec in self:
            if not rec.pancake_id:
                rec._pancake_create_customer_api()
            else:
                rec._pancake_update_customer_api()


    def _pancake_create_customer_api(self):
        self.ensure_one()
        pancake_connector = self.env.ref(
            'advanced_sync_pancake.pancake_connector_1',
            raise_if_not_found=False
        )
        if not pancake_connector:
            raise UserError(_("Pancake connector is not configured"))

        if not pancake_connector.pancake_url or not pancake_connector.pancake_api_key:
            raise UserError(_("Pancake API URL or API Key is missing"))

        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/customers"
        params = {"api_key": pancake_connector.pancake_api_key}
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "name": self.name or "",
            "username": self.name or "",
            "phoneNumber": self.phone or self.mobile or "",
            "createType": "force",
            "emails": [],
            "tags": [],
            "notes": [],
            "dateOfBirth": None,
            "shop_customer_address": [

            ]
        }
        if self.email:
            payload["emails"].append(self.email)
        address_arr = []
        if self.street:
            info_address = self.get_address(self)
            address_arr.append(info_address)
            payload["shop_customer_address"].append({
                "full_address": info_address,
                "full_name": self.name or "",
                "phone_number": self.phone or self.mobile or "",
            })
        if self.child_ids:
            for addr in self.child_ids:
                info_address = self.get_address(addr)
                if info_address in address_arr:
                    continue
                address_arr.append(info_address)
                payload["shop_customer_address"].append({
                    "full_address": info_address or "",
                    "full_name": addr.name or self.name or "",
                    "phone_number": addr.phone or addr.mobile or "",
                })
        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20
            )
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            IrLogging = self.env['ir.logging']
            message = 'url: ' + url + '\nheaders\n' + str(headers) + '\ndata\n\n' + str(
                payload) + '\n\nResponse:\n' + str(response.text) + '\n\nError:\n' + str(e)
            IrLogging.sudo().create({'name': '_pancake_create_customer_api',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self._name),
                                     'func': 'exceptions',
                                     'line': 1})
        result = response.json()
        if result.get('success'):
            self.is_sync_pancake = True
            data = result.get('data', {})
            if data.get('id'):
                self.pancake_id = data.get('id')
                addresses = data.get("shop_customer_addresses") or []
                for addr in addresses:
                    addr_id = addr.get("id")
                    address = addr.get("address", "") # chỉ trả về tầm 20-30 ký tự đầu của địa chỉ
                    full_name = addr.get("full_name", "")
                    matched_child = self.child_ids.filtered(
                        lambda c: (address in c.street) and (c.name and c.name in full_name)
                    )

                    if matched_child:
                        matched_child[0].pancake_address_id = addr_id
                    else:
                        # chỉ set 1 lần nếu chưa có
                        if not self.pancake_address_id:
                            self.pancake_address_id = addr_id



        IrLogging = self.env['ir.logging']

        message = 'url: ' + url + '\nheaders\n' + str(headers) + '\ndata\n\n' + str(payload) + '\n\nResponse:\n' + str(response.text)
        IrLogging.sudo().create({'name': '_pancake_create_customer_api',
                                 'type': 'server',
                                 'message': message,
                                 'path': str(self._name),
                                 'func': 'funcions',
                                 'line': 1})



        return result


    def _pancake_update_customer_api(self):
        self.ensure_one()
        pancake_connector = self.env.ref(
            'advanced_sync_pancake.pancake_connector_1',
            raise_if_not_found=False
        )
        if not pancake_connector:
            raise UserError(_("Pancake connector is not configured"))

        if not pancake_connector.pancake_url or not pancake_connector.pancake_api_key:
            raise UserError(_("Pancake API URL or API Key is missing"))

        url = f"{pancake_connector.pancake_url}/shops/{pancake_connector.shop_id}/customers/{self.pancake_id}"
        params = {"api_key": pancake_connector.pancake_api_key}
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "name": self.name or "",
            "username": self.name or "",
            "phoneNumber": self.phone or self.mobile or "",
            "createType": "force",
            "emails": [],
            "dateOfBirth": None,
            "shop_customer_address": [

            ]
        }
        if self.email:
            payload["emails"].append(self.email)
        if self.pancake_address_id:
            address_arr = []
            info_address = self.get_address(self)
            address_arr.append(info_address)
            payload["shop_customer_address"].append({
                "id": self.pancake_address_id,
                "address": info_address,
                "full_name": self.name or "",
                "phone_number": self.phone or self.mobile or "",
            })
        if self.child_ids:
            for addr in self.child_ids:
                if addr.pancake_address_id:
                    info_address = self.get_address(addr)
                    if info_address in address_arr:
                        continue
                    address_arr.append(info_address)
                    payload["shop_customer_address"].append({
                        "id": addr.pancake_address_id,
                        "address": info_address or "",
                        "full_name": addr.name or "",
                        "phone_number": addr.phone or addr.mobile or "",
                    })
        payload = {
            "customer": payload
        }
        try:
            response = requests.put(
                url,
                params=params,
                headers=headers,
                json=payload,
                timeout=20
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            IrLogging = self.env['ir.logging']
            message = 'url: ' + url + '\nheaders\n' + str(headers) + '\ndata\n\n' + str(
                payload) + '\n\nResponse:\n' + str(response.text) + '\n\nError:\n' + str(e)
            IrLogging.sudo().create({'name': '_pancake_update_customer_api',
                                     'type': 'server',
                                     'message': message,
                                     'path': str(self._name),
                                     'func': 'exceptions',
                                     'line': 1})
        IrLogging = self.env['ir.logging']

        message = 'url: ' + url + '\nheaders\n' + str(headers) + '\nparams\n' + str(params) + '\ndata\n\n' + str(payload) + '\n\nResponse:\n' + str(
            response.text)
        IrLogging.sudo().create({'name': '_pancake_update_customer_api',
                                 'type': 'server',
                                 'message': message,
                                 'path': str(self._name),
                                 'func': 'funcions',
                                 'line': 1})
        result = response.json()
        return {
          "success": True
        }


    def get_address(self, partner):
        address = ''
        data = []
        if partner:
            if partner.street:
                data.append(partner.street)
            if partner.street2:
                data.append(partner.street2)
            if partner.city and partner.city not in data:
                data.append(partner.city)
            if partner.state_id:
                if partner.state_id.name not in data:
                    data.append(partner.state_id.name)
        if len(data) > 0:
            address = ', '.join(e for e in data)
        return address