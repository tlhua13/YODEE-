from odoo import fields, models, api


class PancakeShop(models.Model):
    _name = 'pancake.shop'
    _description = 'Shop'

    name = fields.Char()
    shop_id = fields.Char()
    avatar_url = fields.Char()
    currency_text = fields.Char()
    currency = fields.Char('res.currency')

