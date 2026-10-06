from odoo import api, fields, models

class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    points = fields.Float(related='partner_id.points')
