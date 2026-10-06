from odoo import fields, models, api


class HrEmployeeInherit(models.Model):
    _inherit = "hr.employee"

    employee_code_misa = fields.Char(string="Misa Code")
