# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PosPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [('momo', 'MoMo')]

    momo_partner_code = fields.Char(string='MoMo Partner Code',
        help='Leave empty to use the value from Settings > MoMo.')
    momo_access_key = fields.Char(string='MoMo Access Key',
        help='Leave empty to use the value from Settings > MoMo.')
    momo_secret_key = fields.Char(string='MoMo Secret Key',
        help='Leave empty to use the value from Settings > MoMo.')
    momo_environment = fields.Selection([
        ('test', 'Test (Sandbox)'),
        ('production', 'Production'),
    ], string='MoMo Environment', default='test',
        help='Leave empty to use the value from Settings > MoMo.')
    momo_ipn_url = fields.Char(
        string='MoMo IPN Base URL',
        help='Leave empty to use the value from Settings > MoMo.')
    momo_default_partner_id = fields.Many2one(
        'res.partner',
        string='Default Customer (Khách lẻ)',
        help='Default customer for POS orders without a customer when using MoMo payment. '
             'Leave empty to use the value from Settings > MoMo.',
    )

    def _get_momo_config(self):
        """Get MoMo config: payment method fields first, fallback to res.config.settings"""
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        default_partner_id = self.momo_default_partner_id.id or int(
            ICP.get_param('advanced_momo.default_partner_id', 0)
        )
        return {
            'partner_code': self.momo_partner_code or ICP.get_param('advanced_momo.partner_code', ''),
            'access_key': self.momo_access_key or ICP.get_param('advanced_momo.access_key', ''),
            'secret_key': self.momo_secret_key or ICP.get_param('advanced_momo.secret_key', ''),
            'environment': self.momo_environment or ICP.get_param('advanced_momo.environment', 'test'),
            'ipn_url': self.momo_ipn_url or ICP.get_param('advanced_momo.ipn_url', ''),
            'default_partner_id': default_partner_id,
        }

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        fields_list.append('use_payment_terminal')
        fields_list.append('momo_default_partner_id')
        return fields_list

    @api.onchange('use_payment_terminal')
    def _onchange_use_payment_terminal(self):
        super()._onchange_use_payment_terminal()
        if self.use_payment_terminal != 'momo':
            self.momo_partner_code = False
            self.momo_access_key = False
            self.momo_secret_key = False
            self.momo_environment = 'test'
            self.momo_ipn_url = False
            self.momo_default_partner_id = False
