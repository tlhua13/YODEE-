# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.tools import float_repr


class SaleOrderDiscountInherit(models.TransientModel):
    _inherit = 'sale.order.discount'

    # Field riêng chỉ gồm 2 option (bỏ "On All Order Lines"), dùng để điều khiển
    # field discount_type gốc thay vì sửa trực tiếp selection của nó.
    yodee_discount_type = fields.Selection(
        selection=[
            ('so_discount', "Global Discount"),
            ('amount', "Fixed Amount"),
        ],
        string='Discount Type',
        default='so_discount',
    )
    discount_type_id = fields.Many2one(
        'yodee.discount.type',
        string='Loại chiết khấu',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'discount_type' in fields_list:
            res['discount_type'] = res.get('yodee_discount_type') or 'so_discount'
        return res

    @api.onchange('yodee_discount_type')
    def _onchange_yodee_discount_type(self):
        for wizard in self:
            wizard.discount_type = wizard.yodee_discount_type

    @api.onchange('discount_type_id')
    def _onchange_discount_type_id(self):
        for wizard in self:
            if not wizard.discount_type_id:
                continue
            if wizard.yodee_discount_type == 'amount':
                wizard.discount_amount = wizard.discount_type_id.discount_amount
            else:
                wizard.discount_percentage = wizard.discount_type_id.discount_percentage

    def _prepare_discount_line_values(self, product, amount, taxes, description=None):
        if self.discount_type_id:
            if self.discount_type == 'so_discount':
                description = _(
                    "%(discount_type)s %(percent)s%%",
                    discount_type=self.discount_type_id.name,
                    percent=float_repr(self.discount_percentage * 100, 2)
                )
            elif self.discount_type == 'amount':
                description = self.discount_type_id.name
        return super()._prepare_discount_line_values(product, amount, taxes, description=description)
