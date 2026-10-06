from odoo import fields, models, api
import json

class PancakeWarehouse(models.Model):
    _name = 'pancake.warehouse'

    name = fields.Char()
    phone_number = fields.Char()
    pancake_warehouse_id = fields.Char()
    pancake_custom_id = fields.Char(string="Pancake Code")
    address = fields.Char()
    full_address = fields.Char()
    api_district_id = fields.Char(string='ID quận huyện')
    api_province_id = fields.Char(string='ID tỉnh')
    api_communes_id = fields.Char(string='ID phường xã')
    api_country_code = fields.Char(string='ID quốc gia')
    warehouse_json = fields.Json(copy=False)
    warehouse_json_text = fields.Text(string="Pancake (Text)", compute="_compute_json_text")

    @api.depends("warehouse_json")
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.warehouse_json_text = ""
                if rec.warehouse_json:
                    rec.warehouse_json_text = json.dumps(rec.warehouse_json, indent=4, ensure_ascii=False)
            except Exception:
                rec.warehouse_json_text = ""