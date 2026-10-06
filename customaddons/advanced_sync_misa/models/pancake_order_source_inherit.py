from odoo import api, fields, models, _


class PancakeOrderSourceInherit(models.Model):
    _inherit = 'pancake.order.source'

    misa_debit_account = fields.Many2one('account.account.misa', string='Tài khoản công nợ (debit)',tracking = True)
    misa_credit_account = fields.Many2one('account.account.misa', string='Tài khoản doanh thu (credit)',tracking = True)