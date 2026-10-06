from odoo import models, fields, api


class loyaltyProgramInherit(models.Model):
    _inherit = 'loyalty.program'

    program_type = fields.Selection(default='loyalty')