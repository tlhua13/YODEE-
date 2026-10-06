# -*- coding: utf-8 -*-
import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    momo_transaction_ids = fields.One2many(
        'momo.transaction', 'pos_order_id', string='MoMo Transactions', readonly=True)
    momo_order_id = fields.Many2one(
        'momo.transaction', string='MoMo Order ID', readonly=True)

    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        pos_order = self.env['pos.order'].browse(order_id)
        if pos_order.uuid:
            momo_transactions = self.env['momo.transaction'].sudo().search([
                ('pos_order_name', '=', pos_order.uuid),
                ('pos_order_id', '=', False),
            ])
            if momo_transactions:
                momo_transactions.write({'pos_order_id': pos_order.id})
                pos_order.write({'momo_order_id': momo_transactions[0].id})
                _logger.info("Linked %d MoMo transaction(s) to POS order %s (uuid=%s)",
                             len(momo_transactions), pos_order.name, pos_order.uuid)
        return order_id
