# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettingsInherit(models.TransientModel):
    _inherit = 'res.config.settings'

    momo_partner_code = fields.Char(
        string='MoMo Partner Code',
        config_parameter='advanced_momo.partner_code',
    )
    momo_access_key = fields.Char(
        string='MoMo Access Key',
        config_parameter='advanced_momo.access_key',
    )
    momo_secret_key = fields.Char(
        string='MoMo Secret Key',
        config_parameter='advanced_momo.secret_key',
    )
    momo_environment = fields.Selection([
        ('test', 'Test (Sandbox)'),
        ('production', 'Production'),
    ], string='MoMo Environment', default='test',
        config_parameter='advanced_momo.environment',
    )
    momo_ipn_url = fields.Char(
        string='MoMo IPN Base URL',
        config_parameter='advanced_momo.ipn_url',
        help='Base URL for MoMo webhook callback (e.g. https://yourdomain.com). '
             'Leave empty to use system default web.base.url.',
    )
    momo_default_partner_id = fields.Many2one(
        'res.partner',
        string='Default Customer (Khách lẻ)',
        help='Default customer for POS orders without a customer when using MoMo payment.',
    )

    def set_values(self):
        super().set_values()
        self.env['ir.config_parameter'].sudo().set_param(
            'advanced_momo.default_partner_id',
            self.momo_default_partner_id.id or 0,
        )

    @api.model
    def get_values(self):
        res = super().get_values()
        partner_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'advanced_momo.default_partner_id', default=0,
        ))
        if partner_id and self.env['res.partner'].browse(partner_id).exists():
            res['momo_default_partner_id'] = partner_id
        else:
            res['momo_default_partner_id'] = False
        return res
