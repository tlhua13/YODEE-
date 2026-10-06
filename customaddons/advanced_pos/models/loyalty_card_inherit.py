from odoo import models, fields, api


class loyaltyProgramInherit(models.Model):
    _inherit = 'loyalty.card'

    mark_expired_date = fields.Boolean(
        string='Expired',
        default=False
    )
    expiration_date = fields.Date(
        compute='_compute_expiration_date',
        store=True
    )

    @api.depends('program_id','program_id.date_to')
    def _compute_expiration_date(self):
        for card in self:
            if card.program_id:
                card.expiration_date = card.program_id.date_to
            else:
                card.expiration_date = False
    def cron_reset_expired_points(self):
        today = fields.Date.today()

        cards = self.search([
            ('expiration_date', '!=', False),
            ('expiration_date', '<', today),
            ('mark_expired_date', '=', False),

        ])

        for card in cards:
            card.write({
                'points': 0,
                'mark_expired_date': True,
            })