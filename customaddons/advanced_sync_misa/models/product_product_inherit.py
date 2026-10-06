from odoo import api, fields, models, _


class ProductProductInherit(models.Model):
    _inherit = 'product.product'

    standard_price = fields.Float(tracking=False)