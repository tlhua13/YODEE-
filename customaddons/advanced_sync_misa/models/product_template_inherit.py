from odoo import api, fields, models, _


class ProductInherit(models.Model):
    _inherit = 'product.template'

    misa_id = fields.Char(string='Misa ID', copy=False)
    misa_item_group = fields.Char('Item Group')
    misa_inventory_code = fields.Char('Misa Inventory Code')
    misa_inventory_name = fields.Char('Misa Inventory Name')
    misa_uom_id = fields.Many2one('uom.uom', string='Unit of Measure')

    misa_account_inventory = fields.Many2one('account.account.misa', string='Account Inventory')
    misa_account_revenue = fields.Many2one('account.account.misa', string='Account Revenue')
    misa_account_discount = fields.Many2one('account.account.misa', string='Account Discount')
    misa_account_sale = fields.Many2one('account.account.misa', string='Account Sale')
    misa_account_return = fields.Many2one('account.account.misa', string='Account Return')
    misa_account_expense = fields.Many2one('account.account.misa', string='Account Expense')

    misa_unit_converstion = fields.Char('Unit Converstion')
    misa_unit_convert_rate = fields.Float('Unit Convert Rate')
    misa_unit_calculation = fields.Char('Unit Calculation')
    misa_unit_note = fields.Char('Unit Note')

    misa_features = fields.Selection([('component', 'Component'),
                                      ('product', 'Product'),
                                      ('goods', 'Goods'),
                                      ('service', 'Service'),
                                      ('end_products', 'Finished Product'),
                                      ('equipment', 'Tools and equipment'),
                                      ])
    is_sync_misa = fields.Boolean(default=False, copy=False)
    branch_id = fields.Char(string='Branch ID')
    standard_price = fields.Float(tracking=False)

    def _get_misa_account_by_code(self, code):
        account = self.env['account.account.misa'].search([('code', '=', code)], limit=1)
        return account.id if account else False
    @api.onchange('misa_features')
    def _onchange_misa_features(self):
        if self.misa_features == 'component':
            self.sudo().write({
                'misa_account_inventory': self._get_misa_account_by_code('1561'),
                'misa_account_revenue': self._get_misa_account_by_code('5111'),
                'misa_account_discount': self._get_misa_account_by_code('5211'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('632')
            })
        elif self.misa_features == 'service':
            self.sudo().write({
                'misa_account_inventory': False,
                'misa_account_revenue': self._get_misa_account_by_code('5113'),
                'misa_account_discount': self._get_misa_account_by_code('521'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('632')
            })
        elif self.misa_features == 'goods':
            self.sudo().write({
                'misa_account_inventory': self._get_misa_account_by_code('152'),
                'misa_account_revenue': self._get_misa_account_by_code('5111'),
                'misa_account_discount': self._get_misa_account_by_code('5211'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('621')
            })
        elif self.misa_features == 'end_products':
            self.sudo().write({
                'misa_account_inventory': self._get_misa_account_by_code('1551'),
                'misa_account_revenue': self._get_misa_account_by_code('5112'),
                'misa_account_discount': self._get_misa_account_by_code('5211'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('632')
            })
        elif self.misa_features == 'equipment':
            self.sudo().write({
                'misa_account_inventory': self._get_misa_account_by_code('1531'),
                'misa_account_revenue': self._get_misa_account_by_code('5111'),
                'misa_account_discount': self._get_misa_account_by_code('5211'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('632')
            })
        elif self.misa_features == 'product':
            self.sudo().write({
                'misa_account_inventory': self._get_misa_account_by_code('0'),
                'misa_account_revenue': self._get_misa_account_by_code('5111'),
                'misa_account_discount': self._get_misa_account_by_code('5211'),
                'misa_account_sale': self._get_misa_account_by_code('5213'),
                'misa_account_return': self._get_misa_account_by_code('5212'),
                'misa_account_expense': self._get_misa_account_by_code('0')
            })
        else:
            self.sudo().write({
                'misa_account_inventory': False,
                'misa_account_revenue': False,
                'misa_account_discount': False,
                'misa_account_sale': False,
                'misa_account_return': False,
                'misa_account_expense': False
            })


    def action_tax_update(self):
        view = self.env.ref('advanced_sync_misa.popup_tax_update_view_form')
        active_ids = self.env.context.get('active_ids')
        return {
            'name': _('Tax update'),
            'type': 'ir.actions.act_window',
            'res_model': 'popup.tax.update',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_product_ids': active_ids
            }
        }

    def action_misa_features_update(self):
        view = self.env.ref('advanced_sync_misa.popup_misa_features_update_view_form')
        active_ids = self.env.context.get('active_ids')
        return {
            'name': _('Misa features Update'),
            'type': 'ir.actions.act_window',
            'res_model': 'popup.misa.features.update',
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {
                'default_product_ids': active_ids
            }
        }

    @api.model
    def create(self, vals):
        res = super().create(vals)
        for rec in res:
            if rec.uom_id and not rec.misa_uom_id:
                rec.sudo().write({'misa_uom_id': rec.uom_id.id})
        return res

