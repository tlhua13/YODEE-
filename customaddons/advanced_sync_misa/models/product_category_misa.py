from odoo import fields, models, api


class ProductCategoryMisa(models.Model):
    _name = 'product.category.misa'

    misa_id = fields.Char(string='Misa ID', copy=False)
    name = fields.Char(string='Name')
    code = fields.Char(string='Code')
    code_list = fields.Char(string='Code List')
