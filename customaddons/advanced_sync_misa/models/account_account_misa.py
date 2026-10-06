from odoo import fields, models, api


class AccountAccountMisa(models.Model):
    _name = 'account.account.misa'
    _rec_name = 'display_name'

    misa_id = fields.Char(string='Misa ID', copy=False)
    name = fields.Char(string='Name')
    name_vn = fields.Char(string='Name VN')
    code = fields.Char(string='Code')
    parent_id = fields.Char(string='Parent ID')
    misa_features = fields.Char(string='Features')
    note = fields.Text(string='Note')
    misa_parent = fields.Many2one('account.account.misa', string='Parent', compute='_compute_misa_parent', store=True)

    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('parent_id')
    def _compute_misa_parent(self):
        for record in self:
            record.misa_parent = False
            if record.parent_id:
                misa_parent = self.env['account.account.misa'].sudo().search([('misa_id', '=', record.parent_id)], limit=1)
                if misa_parent:
                    record.misa_parent = misa_parent.id

    @api.depends('code', 'name_vn')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name_vn}"
