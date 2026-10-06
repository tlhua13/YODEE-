# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .pancake_connector import ORDER_STATUS_MAPPING


class PancakeOrderWebhook(models.Model):
    _name = 'pancake.order.webhook'
    _description = 'Pancake Order Webhook'
    _order = 'create_date asc'
    _rec_name = 'pancake_order_id'

    pancake_order_id = fields.Char(string='Pancake Order ID', required=True, index=True)
    # Lưu dạng Char (không phải Selection) để không mất webhook nếu Pancake trả về
    # 1 mã trạng thái nằm ngoài ORDER_STATUS_MAPPING hiện tại.
    pancake_status = fields.Char(string='Pancake Status Code', index=True)
    pancake_status_label = fields.Char(string='Pancake Status', compute='_compute_pancake_status_label')
    raw_data = fields.Text(string='Raw Payload')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('error', 'Error'),
        ('skipped', 'Skipped'),
        ('order_deleted', 'Order Deleted'),
        ('invalid_token', 'Invalid Token'),
    ], string='Status', default='pending', index=True, required=True)
    error_message = fields.Text(string='Error Message')
    processed_date = fields.Datetime(string='Processed Date')

    @api.depends('pancake_status')
    def _compute_pancake_status_label(self):
        for rec in self:
            rec.pancake_status_label = ORDER_STATUS_MAPPING.get(rec.pancake_status, rec.pancake_status)

    def action_set_to_pending(self):
        """Đưa webhook về trạng thái 'pending' để cron xử lý lại (dùng khi cần retry thủ công)."""
        self.write({'state': 'pending', 'error_message': False, 'processed_date': False})
