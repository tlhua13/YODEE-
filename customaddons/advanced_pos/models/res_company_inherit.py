from odoo import fields, models, api

class ResCompanyInherit(models.Model):
    _inherit = 'res.company'


    hotline = fields.Char(string="Hotline")

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ["hotline"]
        return params