from datetime import timedelta

from odoo import fields, models, api


class YodeeIrLoggingInherit(models.Model):
    _inherit = 'ir.logging'

    def _cron_delete_exception_logs(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'yodee.log_retention_days', 7
        ))
        deadline = fields.Datetime.now() - timedelta(days=days)

        self.env.cr.execute(
            "DELETE FROM ir_logging WHERE create_date < %s",
            [deadline],
        )
        self.env.cr.execute(
            "DELETE FROM yodee_ir_logging WHERE create_date < %s",
            [deadline],
        )
        self.env.cr.commit()