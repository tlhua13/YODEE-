from odoo import fields, models, api


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    employee_code_misa = fields.Char(string="Misa Code")