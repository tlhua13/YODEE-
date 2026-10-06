import json
from odoo import models, fields, api, _


class PancakeBranch(models.Model):
    _name = 'pancake.branch'
    _description = 'Brand'

    name = fields.Char(string='Name')
    pancake_supplier_id = fields.Char(string='Pancake id')

    pancake_order_json = fields.Json(string='Dữ liệu đơn hàng Pancake', copy=False)
    pancake_order_json_text = fields.Text(string="Pancake Order (Text)", compute="_compute_json_text")

    @api.depends("pancake_order_json")
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.pancake_order_json_text = ""
                if rec.pancake_order_json:
                    rec.pancake_order_json_text = json.dumps(rec.pancake_order_json, indent=4, ensure_ascii=False)
            except Exception:
                rec.pancake_order_json_text = ""
