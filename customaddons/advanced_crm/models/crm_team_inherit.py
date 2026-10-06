
from odoo import models, fields, api


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    sale_admin_id = fields.Many2one('res.users', string='Sale Admin')
    sale_area_id = fields.Many2many('sale.area', string='Sale Area')

