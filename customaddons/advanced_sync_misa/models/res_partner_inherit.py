from odoo import fields, models, api
from odoo.osv import expression

class ResPartnerInherit(models.Model):
    _inherit = 'res.partner'

    # translated_display_name = fields.Char()

    customer_code = fields.Char(string='Customer Code')


    misa_id = fields.Char(string='Misa ID', copy=False)
    branch_id = fields.Char(string='Branch ID')

    pay_account = fields.Many2one('account.account.misa', string='Pay Account ')
    receive_account = fields.Many2one('account.account.misa', string='Receive Account')

    is_sync_misa = fields.Boolean(default=False, copy=False)
    is_customer = fields.Boolean(default=False, copy=False)
    is_employee = fields.Boolean(default=False, copy=False)
    is_vendor = fields.Boolean(default=False, copy=False)
    is_wholesaler = fields.Boolean(default=False, copy=False, string='Is Wholesale Customer')
    name_wholesaler = fields.Char(string='Wholesaler Customer')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        domain = args or []

        # Call the original name_search first
        partner_ids = super().name_search(name=name, args=args, operator=operator, limit=limit)
        partners = self.browse([p[0] for p in partner_ids])

        # Add additional conditions to search by customer_code and only top-level contacts
        extra_domain = [
            ('parent_id', '=', False),
            ('customer_code', operator, name),
        ]

        domain = expression.AND([domain, extra_domain])

        # Search again with extended domain
        contact_code_partners = self.search(domain, limit=limit)

        partners |= contact_code_partners

        return [(partner.id, partner.display_name) for partner in partners.sudo()]

