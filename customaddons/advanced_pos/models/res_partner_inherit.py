from odoo import models, fields, api

class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    points = fields.Float(compute='_compute_points', string='Loyalty Points')
    noti_expiry = fields.Char(string='Notification Expiry', compute='_compute_notification_expiry')

    def _compute_points(self):
        for partner in self:
            points = 0.0
            loyalty_cards = self.env['loyalty.card'].search([('partner_id', '=', partner.id),
                                                            ('points', '>', '0'),
                                                            ('program_id.active', '=', True)])
            if loyalty_cards:
                points = sum(loyalty_cards.mapped('points'))
            partner.points = points

    def _compute_notification_expiry(self):
        for partner in self:
            noti_expiry = ''
            loyalty_cards = self.env['loyalty.card'].search([('partner_id', '=', partner.id),
                                                             ('points', '>', '0'),
                                                             ('program_id.active', '=', True)], order='expiration_date asc')
            if loyalty_cards:
                nearest_card = loyalty_cards[0]
                if nearest_card.expiration_date:
                    points = int(nearest_card.points)
                    points_str = f"{points:,}".replace(",", ".")
                    noti_expiry = (
                        f"{points_str} (exp: {nearest_card.expiration_date.strftime('%d-%m-%Y')})"
                    )
            partner.noti_expiry = noti_expiry

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ["noti_expiry"]
        return params

    def is_integer(self, value):
        if int(value) == value:
            return int(value)
        else:
            return round(value, 2)