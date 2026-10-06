from odoo import fields, models, api
import json
import requests
import logging

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    name = fields.Char(string='Tên sản phẩm', required=True, translate=True, tracking=True)
    pancake_product_template_id = fields.Many2one('pancake.product.template', string='Sản phẩm mẫu')
    pancake_product_id = fields.Char( string='Pancake Product ID')

    #todo thêm vào do odoo barcode không cho trùng còn pancake thì cho
    pancake_barcode = fields.Char(string='Pancake Barcode')


    pancake_order_json = fields.Json(string='Dữ liệu Pancake', copy=False)
    pancake_order_json_text = fields.Text(string="Pancake Order (Text)", compute="_compute_json_text")

    # pancake_branch_ids = fields.Many2many(
    #     'pancake.branch',
    #     string='Branches',
    #     compute="_compute_pancake_branches",
    #     store=False
    # )

    pancake_brand_ids = fields.Many2many('pancake.branch',string='Brands')

    combo_product = fields.Many2many(
        'product.template',
        'product_template_combo_rel',
        'parent_template_id',
        'child_template_id',
        string='Product combo'
    )

    @api.depends("pancake_order_json")
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.pancake_order_json_text = ""
                if rec.pancake_order_json:
                    rec.pancake_order_json_text = json.dumps(rec.pancake_order_json, indent=4, ensure_ascii=False)
            except Exception:
                rec.pancake_order_json_text = ""

    pancake_template_name = fields.Char(
        string="Tên Sản phẩm mẫu",
        related='pancake_product_template_id.name',
        store=True
    )

    @api.model
    def create(self, vals):
        if vals.get('uom_id') == 1 or vals.get('uom_po_id') == 1:
            uom_chiec = self.env['uom.uom'].search([('name', '=', 'Chiếc')], limit=1)
            if uom_chiec:
                vals['uom_id'] = uom_chiec.id
                vals['uom_po_id'] = uom_chiec.id
        res = super().create(vals)
        for rec in res:
            if rec.type == 'consu' and not rec.is_storable:
                rec.is_storable = True
        return res


    def action_change_uom(self):
        form_view_id = self.env.ref('advanced_sync_pancake.view_product_change_uom_form').id
        return {
            'name': "Cập nhật Đơn vị",
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'views': [(form_view_id, 'form')],
            'res_model': 'product.change.uom',
            'context': {
                'active_id': self.id,
            },
            'target': 'new',
        }
