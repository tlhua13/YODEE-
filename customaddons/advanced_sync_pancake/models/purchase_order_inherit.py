from odoo import fields, models, api


class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'


    @api.model
    def create(self, vals):
        res = super().create(vals)
        for rec in res:
            rec.sudo()._compute_tax_totals()
            for line in rec.order_line:
                line.sudo()._compute_amount()

        return res