
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError, AccessError

class CrmStageInherit(models.Model):
    _inherit = 'crm.stage'
    _description = 'crm stage inherit'

    enable_condition = fields.Boolean(string="Enable Condition", default=False)
    require_email = fields.Boolean(string="Enable require Email")
    require_phone = fields.Boolean(string="Enable require Phone")
    require_address = fields.Boolean(string="Enable require address")
    require_quotation = fields.Boolean(string="Enable require quotation")

    def is_lead_match(self, lead):
        self.ensure_one()

        if not self.enable_condition:
            return False

        if self.require_email:
            if not lead.email_from:
                return False

        if self.require_email and self.require_phone: # =------stage 1---------
            if not lead.email_from or not lead.phone:
                return False

        if self.require_email and self.require_phone and self.require_address: # =------stage 2---------
            if not lead.email_from or not lead.phone or not lead.street:
                return False

        if self.require_email and self.require_phone and self.require_address and self.require_quotation:
            if not lead.email_from or not lead.phone or not lead.street:
                return False

            has_quotation = self.env['sale.order'].search_count([
                ('opportunity_id', '=', lead.id),
                ('state', 'not in', ['cancel'])
            ])
            if not has_quotation:
                return False

        return True

    # auto update when stage is changed
    def write(self, vals):
        res = super().write(vals)

        trigger_fields = {
            'enable_condition',
            'require_email',
            'require_phone',
            'require_address',
            'require_quotation',
            'sequence',
        }

        if trigger_fields & vals.keys():
            leads = self.env['crm.lead'].search([])
            leads._auto_update_stage()

        return res

    @api.constrains(
        'require_email',
        'require_phone',
        'require_address',
        'require_quotation'
    )
    def _check_duplicate_conditions(self):
        for rec in self:
            domain = [
                ('id', '!=', rec.id),
                ('require_email', '=', rec.require_email),
                ('require_phone', '=', rec.require_phone),
                ('require_address', '=', rec.require_address),
                ('require_quotation', '=', rec.require_quotation),
            ]

            dup = self.search(domain, limit=1)
            if dup:
                raise ValidationError(
                    f"Stage '{dup.name}' đã có cùng cấu hình điều kiện."
                )
