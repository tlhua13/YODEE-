
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError, AccessError

class ProductPricelistInherit(models.Model):
    _inherit = 'product.pricelist'

    sale_team_ids = fields.Many2many(
        'crm.team',
        string="Sale Teams"
    )
