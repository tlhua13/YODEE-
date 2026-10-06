# -*- coding: utf-8 -*-
from odoo import fields, models


class YodeeDiscountType(models.Model):
    _name = 'yodee.discount.type'
    _description = 'Loại chiết khấu'

    name = fields.Char(string='Tên loại chiết khấu', required=True)
    discount_percentage = fields.Float(string='% Chiết khấu mặc định')
    discount_amount = fields.Float(string='Giá trị chiết khấu mặc định')
