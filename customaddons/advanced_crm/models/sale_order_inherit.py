from odoo import api, fields, models

class SaleOrderInherit(models.Model):
    _inherit = 'sale.order'

    @api.model
    def create(self, vals):
        order = super().create(vals)
        if order.opportunity_id:
            order.opportunity_id._auto_update_stage()
        return order