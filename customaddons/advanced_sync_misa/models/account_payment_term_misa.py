from odoo import fields, models, api


class AccountPaymentTerm(models.Model):
    _name = 'account.payment.term.misa'
    _rec_name = 'name'

    misa_id = fields.Char(string='Misa ID', copy=False)
    due_time = fields.Integer(string='Due Time')
    discount_time = fields.Integer(string='Discount Time')
    discount_percent = fields.Float(string='Discount Percent')
    code = fields.Char(string='Code')
    name = fields.Char(string='Name')
