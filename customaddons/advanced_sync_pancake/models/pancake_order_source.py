from odoo import fields, models, api


class PancakeOrderSource(models.Model):
    _name = 'pancake.order.source'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(tracking = True)
    pancake_id = fields.Char(tracking = True)
    parent_id = fields.Char(tracking = True)
    parent_source_id = fields.Many2one('pancake.order.source', string='Parent Source',tracking = True)
    is_b2b_business = fields.Boolean(string='Is B2B Business', default=False,tracking = True)
    default_customer =  fields.Many2one('res.partner', string = "Misa Customer",tracking = True)