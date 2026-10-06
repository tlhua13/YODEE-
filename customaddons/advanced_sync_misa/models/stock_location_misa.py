from odoo import fields, models, api


class StockLocationMisa(models.Model):
    _name = 'stock.location.misa'
    _description = 'Stock Location Misa'

    misa_id = fields.Char(string='Misa ID', copy=False)
    branch_id = fields.Char(string='Branch ID')
    name = fields.Char(string='Name')
    code = fields.Char(string='Code')
    address = fields.Char(string='Address')
    misa_inventory_code = fields.Char('Tài khoản kho')
    state = fields.Char(string='state')
    active = fields.Boolean('Active', default=True)
    misa_account_inventory = fields.Many2one('account.account.misa', string='Account Inventory')