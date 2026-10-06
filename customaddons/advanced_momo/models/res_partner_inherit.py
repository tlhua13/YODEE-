from odoo import models, fields, api


class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    points = fields.Float(compute='_compute_points', string='Loyalty Points', store=True)

    def _compute_points(self):
        for partner in self:
            points = 0.0
            loyalty_cards = self.env['loyalty.card'].search([('partner_id', '=', partner.id),
                                                            ('points', '>', '0'),
                                                            ('program_id.active', '=', True),
                                                            '|',
                                                            ('expiration_date', '>=', fields.Date().context_today(self)),
                                                            ('expiration_date', '=', False)])
            if loyalty_cards:
                points = sum(loyalty_cards.mapped('points'))
            partner.points = points
