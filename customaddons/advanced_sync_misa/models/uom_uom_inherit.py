from odoo import fields, models, api


class UomUomInherit(models.Model):
    _inherit = 'uom.uom'

    misa_id = fields.Char(string='Misa ID', copy=False)
    exchange_rate_operator = fields.Char(string='Exchange rate operator', copy=False)
    convert_rate = fields.Char(string='Convert Rate', copy=False)
