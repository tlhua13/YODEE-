import json
import requests
import logging
from odoo import models, fields, _
from .yodee_ir_logging import YodeeIrLogging

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pancake_url = fields.Char(string='API URL', config_parameter='advanced_sync_pancake.pancake_url', default='https://pos.pages.fm/api/v1')
    pancake_api_key = fields.Char(string="API Key", config_parameter='advanced_sync_pancake.pancake_api_key')
    pancake_webhook_token = fields.Char(string="Webhook Token", config_parameter='advanced_sync_pancake.pancake_webhook_token',
                                         help="Token dùng để xác thực webhook gửi tới /pancake/order/webhook (so khớp với header X-Webhook-Token)")

    def get_info_pancake(self):
        """
        Get shop information from Pancake API and log to yodee.ir.logging
        """
        try:
            api_url = self.pancake_url
            api_key = self.pancake_api_key

            if not api_url or not api_key:
                raise ValueError("API URL and API Key must be configured")

            # Build the endpoint URL
            url = f"{api_url}/shops"
            params = {'api_key': api_key}

            # Make the GET request
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Parse response
            data = response.json()
            if "shops" in data:
                for shop in data["shops"]:
                    shop_id = shop['id']
                    pancake = self.env['pancake.shop'].sudo().search([('shop_id', '=', shop_id)])
                    if pancake:
                        pancake.write({
                            'name': shop['name'],
                            'currency_text': shop['currency'],
                            'avatar_url': shop['avatar_url'],
                        })
                    else:
                        self.env['pancake.shop'].sudo().create({
                            'name': shop['name'],
                            'shop_id': shop_id,
                            'currency_text': shop['currency'],
                            'avatar_url': shop['avatar_url'],

                        })

            # Save log into yodee.ir.logging
            logging = self.env['yodee.ir.logging'].sudo()
            logging.log_outgoing_request(response)
            # Show success notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Shop information retrieved successfully'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except requests.exceptions.RequestException as e:
            _logger.error(f"Pancake API Request Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to connect to Pancake API: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

        except Exception as e:
            _logger.error(f"Unexpected Error: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('An unexpected error occurred: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
