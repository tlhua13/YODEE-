from odoo import models, fields, api
class HrEmployeeInherit(models.Model):
    _inherit = 'hr.employee'
    pancake_employee_id = fields.Char(string='Employee ID')



class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    pancake_employee_id = fields.Char(string='Employee ID')