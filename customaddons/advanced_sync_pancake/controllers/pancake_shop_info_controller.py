import requests
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)
import json


class PancakeController(http.Controller):

    @http.route('/pancake/get_shop_info', type='json', auth='user', methods=['GET'])
    def get_shop_info(self):
        """
        Get shop information from Pancake API
        """
        try:
            # Get configuration parameters
            api_url = request.env['ir.config_parameter'].sudo().get_param('advanced_sync_pancake.pancake_url')
            api_key = request.env['ir.config_parameter'].sudo().get_param('advanced_sync_pancake.pancake_api_key')

            if not api_url or not api_key:
                return {
                    'success': False,
                    'message': 'API URL or API Key is not configured'
                }

            # Build the endpoint URL
            endpoint = f"{api_url}/shops"
            params = {'api_key': api_key}

            # Make the GET request
            response = requests.get(endpoint, params=params, timeout=30)

            # Check response status
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'data': data,
                    'message': 'Shop information retrieved successfully'
                }
            else:
                _logger.error(f"Pancake API Error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'message': f"API Error: {response.status_code}",
                    'error': response.text
                }

        except requests.exceptions.RequestException as e:
            _logger.error(f"Request Error: {str(e)}")
            return {
                'success': False,
                'message': f"Request Error: {str(e)}"
            }
        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'success': False,
                'message': f"Unexpected Error: {str(e)}"
            }

    @http.route('/pancake/order/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def pancake_order_webhook(self, **kwargs):
        """
        Nhận webhook đơn hàng từ Pancake.
        Endpoint này chỉ lưu lại payload thô vào model 'pancake.order.webhook',
        việc xử lý (gọi pancake.connector.get_order_by_id để tạo/cập nhật sale.order)
        được thực hiện sau đó bởi cron _cron_process_pancake_order_webhook.

        Nếu request có header 'X-Webhook-Token' và khác với token cấu hình ở
        system parameter 'advanced_sync_pancake.pancake_webhook_token', webhook vẫn
        được lưu lại (để không mất dữ liệu) nhưng state='invalid_token' nên sẽ
        KHÔNG được cron xử lý (cron chỉ lấy các webhook state='pending').
        """
        logging_obj = request.env['yodee.ir.logging'].sudo()
        try:
            raw_body = request.httprequest.data

            try:
                data = json.loads(raw_body) if raw_body else {}
            except ValueError:
                _logger.error("Pancake order webhook: invalid JSON payload: %s", raw_body)
                logging_obj.log_incoming_request(
                    request=request.httprequest,
                    data=json.dumps({'success': False, 'message': 'Invalid JSON payload'}),
                    source='pancake', status=400)
                return request.make_json_response({'success': False, 'message': 'Invalid JSON payload'}, status=400)

            order_id = data.get('order_id') or data.get('id') or (data.get('order') or {}).get('id')
            if not order_id:
                _logger.warning("Pancake order webhook: missing order id in payload: %s", data)
                logging_obj.log_incoming_request(
                    request=request.httprequest,
                    data=json.dumps({'success': False, 'message': 'Missing order id'}),
                    source='pancake', status=400)
                return request.make_json_response({'success': False, 'message': 'Missing order id'}, status=400)

            header_token = request.httprequest.headers.get('X-Webhook-Token')
            configured_token = request.env['ir.config_parameter'].sudo().get_param(
                'advanced_sync_pancake.pancake_webhook_token')
            webhook_state = 'pending'
            if not header_token or (header_token and configured_token and header_token != configured_token):
                _logger.warning("Pancake order webhook: invalid token for order %s", order_id)
                webhook_state = 'invalid_token'

            order_status = data.get('status')
            request.env['pancake.order.webhook'].sudo().create({
                'pancake_order_id': str(order_id),
                'pancake_status': str(order_status) if order_status is not None else False,
                'raw_data': json.dumps(data),
                'state': webhook_state,
            })

            logging_obj.log_incoming_request(
                request=request.httprequest,
                data=json.dumps({'success': True}),
                source='pancake', status=200)

            return request.make_json_response({'success': True})
        except Exception as e:
            _logger.error("Pancake order webhook: unexpected error: %s", str(e))
            logging_obj.log_incoming_request(
                request=request.httprequest,
                data=json.dumps({'success': False, 'message': str(e)}),
                source='pancake', status=500)
            return request.make_json_response({'success': False, 'message': 'Internal error'}, status=500)