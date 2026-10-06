
from odoo import models, fields, api


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    sale_area_id = fields.Many2one('sale.area' ,compute='_compute_partner_detail', store=True, readonly=False, string= "Sale Area")
    name_wholesaler = fields.Char(compute='_compute_partner_detail', store=True, readonly=False, string= "Wholesaler Customer")
    sale_admin_id = fields.Many2one(
        'res.users',
        string='Sale Admin',
        compute='_compute_sale_info',
        store=True
    )

    sale_manager_id = fields.Many2one(
        'res.users',
        string='Sale Leader',
        compute='_compute_sale_info',
        store=True
    )

    @api.depends('user_id', 'team_id')
    def _compute_sale_info(self):
        for lead in self:
            team = lead.team_id

            lead.sale_admin_id = team.sale_admin_id if team else False
            lead.sale_manager_id = team.user_id if team else False

    # auto update when any field is changed
    def write(self, vals):
        res = super().write(vals)

        trigger_fields = {
            'email_from',
            'phone',
            'street',
            'sale_area_id',
        }

        if trigger_fields & vals.keys():
            self._auto_update_stage()

        partner_trigger_fields = {'sale_area_id'}

        if partner_trigger_fields & vals.keys():
            for rec in self:
                if rec.partner_id:
                    update_vals = {}

                    # Chỉ update nếu partner chưa có
                    if rec.sale_area_id and not rec.partner_id.sale_area_id:
                        update_vals['sale_area_id'] = rec.sale_area_id.id

                    if update_vals:
                        rec.partner_id.write(update_vals)

        return res

    def _auto_update_stage(self):
        for lead in self:
            stages = self.env['crm.stage'].search([
                ('enable_condition', '=', True)
            ], order='sequence ASC')

            matched_stage = False

            for stage in stages:
                if stage.is_lead_match(lead):
                    matched_stage = stage

            if matched_stage and lead.stage_id != matched_stage:
                lead.stage_id = matched_stage

    @api.model
    def create(self, vals):
        lead = super().create(vals)
        lead._auto_update_stage()
        return lead

    @api.depends(
        'partner_id',
        'partner_id.sale_area_id',
        'partner_id.name_wholesaler'
    )
    def _compute_partner_detail(self):
        for rec in self:
            if rec.partner_id and rec.partner_id.sale_area_id:
                rec.sale_area_id = rec.partner_id.sale_area_id
            if rec.partner_id and rec.partner_id.name_wholesaler:
                rec.name_wholesaler = rec.partner_id.name_wholesaler