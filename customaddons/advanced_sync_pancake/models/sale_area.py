from odoo import fields, models, api


class SaleArea(models.Model):
    _name = 'sale.area'
    _description = 'Khu vực bán hàng'

    name = fields.Char(string='Name', required=True)
