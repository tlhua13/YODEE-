from odoo import fields, models, api


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    code_misa = fields.Char(string="Misa Code")
    payment_term_misa_id = fields.Many2one('account.payment.term.misa',string="Misa Payment Term")
