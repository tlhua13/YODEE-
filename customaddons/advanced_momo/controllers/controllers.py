# -*- coding: utf-8 -*-
import json
import logging
import traceback

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AdvancedSyncMOMO(http.Controller):

    @http.route('/api/momo/call_back_data', type="json", auth="public", website=False, methods=['POST'], csrf=False)
    def callback_momo(self):
        """Handle MoMo IPN (Instant Payment Notification) callback.
        Called directly by MoMo servers (not via Odoo RPC).
        """
        data = {}
        try:
            data = request.get_json_data()
            # Log the callback
            request.env['ir.logging'].sudo().create({
                'name': 'callback_momo_received',
                'type': 'server',
                'message': f"response\n: {json.dumps(data)}",
                'path': 'api/momo/call_back_data',
                'func': 'callback_momo',
                'line': 1,
            })

            order_id = data.get('orderId', '')
            result_code = data.get('resultCode')
            trans_id = str(data.get('transId', ''))

            # Find the transaction
            transaction = request.env['momo.transaction'].sudo().search([
                ('name', '=', order_id)
            ], limit=1)

            if not transaction:
                _logger.warning("MoMo callback: transaction not found for orderId=%s", order_id)
                return json.dumps({
                    "Success": False,
                    "ErrorCode": "NotFound",
                    "ErrorMessage": "Transaction not found"
                })

            # Verify signature
            payment_method = transaction.payment_method_id
            if payment_method:
                momo_cfg = payment_method._get_momo_config()
                if momo_cfg['access_key'] and momo_cfg['secret_key']:
                    is_valid = request.env['momo.transaction'].sudo().verify_callback_signature(
                        data,
                        momo_cfg['access_key'],
                        momo_cfg['secret_key']
                    )
                    if not is_valid:
                        _logger.warning("MoMo callback: invalid signature for orderId=%s", order_id)
                        transaction.sudo().write({
                            'state': 'failed',
                            'message': 'Invalid signature',
                            'callback_data': json.dumps(data),
                        })
                        return json.dumps({
                            "Success": False,
                            "ErrorCode": "InvalidSignature",
                            "ErrorMessage": "Signature verification failed"
                        })

            # Update transaction based on resultCode
            if result_code == 0:
                transaction.sudo().write({
                    'state': 'done',
                    'result_code': result_code,
                    'trans_id': trans_id,
                    'message': data.get('message', 'Success'),
                    'callback_data': json.dumps(data),
                })
            else:
                transaction.sudo().write({
                    'state': 'failed',
                    'result_code': result_code,
                    'trans_id': trans_id,
                    'message': data.get('message', 'Failed'),
                    'callback_data': json.dumps(data),
                })

            # Log the callback
            name = 'callback_momo_success' if result_code == 0 else 'callback_momo_failed'
            request.env['ir.logging'].sudo().create({
                'name': name,
                'type': 'server',
                'message': f"response: {json.dumps(data)}\nstate: {transaction.state}",
                'path': 'api/momo/call_back_data',
                'func': 'callback_momo',
                'line': 1,
            })

            return json.dumps({
                "Success": True,
                "ErrorMessage": ""
            })

        except Exception as e:
            error = traceback.format_exc()
            _logger.error("MoMo callback error: %s\nData: %s", error, str(data))
            request.env['ir.logging'].sudo().create({
                'type': 'server',
                'name': 'callback_momo',
                'path': 'api/momo/call_back_data',
                'line': 1,
                'func': 'exception',
                'message': f"{error}\n{str(data)}"
            })
            return json.dumps({
                "Success": False,
                "ErrorMessage": str(e)
            })

    @http.route('/api/momo/create_payment', type="json", auth="user", methods=['POST'], csrf=False)
    def create_momo_payment(self, payment_method_id=None, amount=None, order_name='', session_id=False):
        """Create a MoMo payment request from POS.
        Called via Odoo rpc() from the POS frontend.
        """
        if not payment_method_id:
            return {'success': False, 'message': 'Missing payment_method_id'}
        if not amount:
            return {'success': False, 'message': 'Missing amount'}

        # Validate MoMo config before calling API
        payment_method = request.env['pos.payment.method'].sudo().browse(payment_method_id)
        if not payment_method.exists():
            return {'success': False, 'message': 'Payment method not found'}

        momo_cfg = payment_method._get_momo_config()
        if not momo_cfg.get('partner_code'):
            return {'success': False, 'message': 'MoMo Partner Code is not configured. Go to Settings > MoMo.'}
        if not momo_cfg.get('access_key'):
            return {'success': False, 'message': 'MoMo Access Key is not configured. Go to Settings > MoMo.'}
        if not momo_cfg.get('secret_key'):
            return {'success': False, 'message': 'MoMo Secret Key is not configured. Go to Settings > MoMo.'}

        try:
            result = request.env['momo.transaction'].sudo().create_momo_payment(
                payment_method_id, amount, order_name, session_id
            )
            return result
        except Exception as e:
            _logger.error("create_momo_payment exception: %s", traceback.format_exc())
            return {'success': False, 'message': str(e)}

    @http.route('/api/momo/force_done', type="json", auth="user", methods=['POST'], csrf=False)
    def force_done_momo(self, transaction_id=None):
        """Force a MoMo transaction as done (manual confirmation by cashier)."""
        if not transaction_id:
            return {'success': False, 'message': 'No transaction ID'}

        transaction = request.env['momo.transaction'].sudo().browse(transaction_id)
        if not transaction.exists():
            return {'success': False, 'message': 'Transaction not found'}

        transaction.write({
            'state': 'done',
            'is_manual': True,
            'message': 'Manual confirmation by cashier',
        })
        return {'success': True}

    @http.route('/api/momo/check_status', type="json", auth="user", methods=['POST'], csrf=False)
    def check_momo_status(self, transaction_id=None):
        """Check MoMo transaction status (polled by POS frontend)."""
        if not transaction_id:
            return {'state': 'failed', 'message': 'No transaction ID'}

        return request.env['momo.transaction'].sudo().check_transaction_status(transaction_id)
