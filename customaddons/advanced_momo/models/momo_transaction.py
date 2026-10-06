# -*- coding: utf-8 -*-
import base64
import hmac
import hashlib
import io
import json
import uuid
import logging
from collections import OrderedDict

import qrcode
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

MOMO_API_URLS = {
    'production': 'https://payment.momo.vn/v2/gateway/api/create',
    'test': 'https://test-payment.momo.vn/v2/gateway/api/create',
}


class MomoTransaction(models.Model):
    _name = 'momo.transaction'
    _description = 'MoMo Payment Transaction'
    _order = 'create_date desc'

    name = fields.Char(string='Order ID', index=True, default='New', readonly=True, copy=False)
    request_id = fields.Char(string='Request ID', required=True, index=True)
    partner_code = fields.Char(string='Partner Code')
    amount = fields.Float(string='Amount', required=True)
    order_info = fields.Char(string='Order Info')
    pay_url = fields.Char(string='Pay URL')
    qr_code_url = fields.Char(string='QR Code URL')
    deeplink = fields.Char(string='Deeplink')
    result_code = fields.Integer(string='Result Code', default=-1)
    message = fields.Char(string='Message')
    trans_id = fields.Char(string='MoMo Transaction ID', index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('done', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', index=True)
    is_manual = fields.Boolean(string='Manual Confirmation', default=False)
    payment_method_id = fields.Many2one('pos.payment.method', string='Payment Method')
    pos_order_id = fields.Many2one('pos.order', string='POS Order', readonly=True, index=True)
    pos_order_name = fields.Char(string='POS Order Reference')
    pos_session_id = fields.Many2one('pos.session', string='POS Session')
    callback_data = fields.Text(string='Callback Data')
    extra_data = fields.Char(string='Extra Data', default='')
    qr_code_image = fields.Binary(string='QR Code Image', attachment=True)
    momo_request_json = fields.Json(string='Dữ liệu gửi MoMo API', copy=False)
    momo_response_json = fields.Json(string='Dữ liệu trả về MoMo API', copy=False)
    momo_signature_json = fields.Json(string='Dữ liệu chữ ký MoMo', copy=False)
    momo_request_text = fields.Text(string='Request (Text)', compute='_compute_json_text')
    momo_response_text = fields.Text(string='Response (Text)', compute='_compute_json_text')
    momo_signature_text = fields.Text(string='Signature (Text)', compute='_compute_json_text')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('momo.transaction') or 'New'
        return super().create(vals_list)

    @api.depends('momo_request_json', 'momo_response_json', 'momo_signature_json')
    def _compute_json_text(self):
        for rec in self:
            try:
                rec.momo_request_text = json.dumps(rec.momo_request_json, indent=4, ensure_ascii=False) if rec.momo_request_json else ""
            except Exception:
                rec.momo_request_text = ""
            try:
                rec.momo_response_text = json.dumps(rec.momo_response_json, indent=4, ensure_ascii=False) if rec.momo_response_json else ""
            except Exception:
                rec.momo_response_text = ""
            try:
                rec.momo_signature_text = json.dumps(rec.momo_signature_json, indent=4, ensure_ascii=False) if rec.momo_signature_json else ""
            except Exception:
                rec.momo_signature_text = ""

    def action_print_qr(self):
        """Print the MoMo QR code as PDF"""
        return self.env.ref('advanced_momo.action_report_momo_qr').report_action(self)

    @api.model
    def _generate_qr_base64(self, data_url):
        """Generate a QR code PNG image as a base64 data URI from the given URL."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(data_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    @api.model
    def generate_signature(self, data, access_key, secret_key):
        """Generate MoMo HMAC-SHA256 signature (from test_signature.py)"""
        raw_data = OrderedDict({
            "accessKey": access_key,
            "amount": str(int(data["amount"])),
            "extraData": data.get("extraData", ""),
            "ipnUrl": data["ipnUrl"],
            "orderId": data["orderId"],
            "orderInfo": data["orderInfo"],
            "partnerCode": data["partnerCode"],
            "redirectUrl": data["redirectUrl"],
            "requestId": data["requestId"],
            "requestType": data["requestType"],
        })

        raw_signature = "&".join(f"{k}={v}" for k, v in raw_data.items())

        signature = hmac.new(
            secret_key.encode("utf-8"),
            raw_signature.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature, raw_signature

    @api.model
    def verify_callback_signature(self, data, access_key, secret_key):
        """Verify MoMo IPN callback signature"""
        raw_data = OrderedDict({
            "accessKey": access_key,
            "amount": str(data.get("amount", "")),
            "extraData": data.get("extraData", ""),
            "message": data.get("message", ""),
            "orderId": data.get("orderId", ""),
            "orderInfo": data.get("orderInfo", ""),
            "orderType": data.get("orderType", ""),
            "partnerCode": data.get("partnerCode", ""),
            "payType": data.get("payType", ""),
            "requestId": data.get("requestId", ""),
            "responseTime": str(data.get("responseTime", "")),
            "resultCode": str(data.get("resultCode", "")),
            "transId": str(data.get("transId", "")),
        })

        raw_signature = "&".join(f"{k}={v}" for k, v in raw_data.items())

        expected_signature = hmac.new(
            secret_key.encode("utf-8"),
            raw_signature.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return expected_signature == data.get("signature", "")

    @api.model
    def create_momo_payment(self, payment_method_id, amount, order_name, session_id=False):
        """Create a MoMo payment request and return QR code URL"""
        _logger.info("=== create_momo_payment START === payment_method_id=%s, amount=%s, order_name=%s, session_id=%s",
                      payment_method_id, amount, order_name, session_id)

        payment_method = self.env['pos.payment.method'].browse(payment_method_id)
        _logger.info("Payment method: id=%s, name=%s, use_payment_terminal=%s",
                      payment_method.id, payment_method.name, payment_method.use_payment_terminal)

        # Get MoMo config (payment method fields or fallback to res.config.settings)
        momo_cfg = payment_method._get_momo_config()
        _logger.info("MoMo config: partner_code=%s, access_key=%s, environment=%s, ipn_url=%s",
                      momo_cfg['partner_code'],
                      '***' if momo_cfg['access_key'] else '(empty)',
                      momo_cfg['environment'],
                      momo_cfg['ipn_url'])

        if not momo_cfg['partner_code'] or not momo_cfg['access_key'] or not momo_cfg['secret_key']:
            _logger.error("MoMo config incomplete: partner_code=%s, access_key=%s, secret_key=%s",
                          bool(momo_cfg['partner_code']), bool(momo_cfg['access_key']), bool(momo_cfg['secret_key']))
            raise UserError(_("MoMo payment is not configured. Please set Partner Code, Access Key and Secret Key in Settings > MoMo or on the Payment Method."))

        request_id = str(uuid.uuid4())
        _logger.info("Generated request_id=%s", request_id)

        # Create transaction record first to get auto-sequence name
        transaction = self.create({
            'request_id': request_id,
            'partner_code': momo_cfg['partner_code'],
            'amount': amount,
            'state': 'pending',
            'payment_method_id': payment_method_id,
            'pos_order_name': order_name,
            'pos_session_id': session_id,
        })
        order_id = transaction.name
        _logger.info("Transaction created: id=%s, name=%s", transaction.id, order_id)

        base_url = momo_cfg['ipn_url'] or self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        ipn_url = f"{base_url}/api/momo/call_back_data"
        redirect_url = base_url
        _logger.info("URLs: base_url=%s, ipn_url=%s", base_url, ipn_url)

        payload = {
            "partnerCode": momo_cfg['partner_code'],
            "requestId": request_id,
            "amount": int(amount),
            "orderId": order_id,
            "orderInfo": f"Thanh toan {order_id}",
            "redirectUrl": "",
            "ipnUrl": ipn_url,
            "requestType": "captureWallet",
            "extraData": "",
            "lang": "vi",
        }

        signature, raw_signature = self.generate_signature(payload, momo_cfg['access_key'], momo_cfg['secret_key'])
        payload["signature"] = signature

        transaction.write({
            'order_info': payload['orderInfo'],
            'momo_signature_json': {
                'raw_signature': raw_signature,
                'signature': signature,
            },
        })

        # Call MoMo API
        momo_env = momo_cfg['environment'] or 'test'
        api_url = MOMO_API_URLS.get(momo_env, MOMO_API_URLS['test'])
        _logger.info("Calling MoMo API: url=%s, env=%s", api_url, momo_env)

        try:
            _logger.info("MoMo API Request: %s", json.dumps(payload))
            transaction.write({'momo_request_json': payload})

            response = requests.post(api_url, json=payload, timeout=30)
            _logger.info("MoMo API HTTP status: %s", response.status_code)
            result = response.json()
            _logger.info("MoMo API Response: %s", json.dumps(result))

            transaction.write({
                'momo_response_json': result,
                'result_code': result.get('resultCode', -1),
                'message': result.get('message', ''),
                'pay_url': result.get('payUrl', ''),
                'qr_code_url': result.get('qrCodeUrl', ''),
                'deeplink': result.get('deeplink', ''),
            })

            if result.get('resultCode') == 0:
                _logger.info("=== create_momo_payment SUCCESS === qr_code_url=%s, pay_url=%s",
                              result.get('qrCodeUrl', ''), result.get('payUrl', ''))

                # Generate QR code image from qrCodeUrl
                qr_image_url = result.get('qrCodeUrl') or result.get('payUrl', '')
                qr_code_base64 = ''
                if qr_image_url:
                    try:
                        qr_code_base64 = self._generate_qr_base64(qr_image_url)
                        # Store raw base64 image (without data URI prefix) for PDF report
                        if qr_code_base64.startswith('data:image/png;base64,'):
                            raw_b64 = qr_code_base64.split(',', 1)[1]
                            transaction.write({'qr_code_image': raw_b64})
                    except Exception as e:
                        _logger.warning("Failed to generate QR code image: %s", str(e))

                return {
                    'success': True,
                    'transaction_id': transaction.id,
                    'order_id': order_id,
                    'request_id': request_id,
                    'pay_url': result.get('payUrl', ''),
                    'qr_code_url': result.get('qrCodeUrl', ''),
                    'qr_code_base64': qr_code_base64,
                    'deeplink': result.get('deeplink', ''),
                    'amount': amount,
                }
            else:
                _logger.warning("=== create_momo_payment FAILED === resultCode=%s, message=%s",
                                result.get('resultCode'), result.get('message'))
                transaction.write({'state': 'failed'})
                return {
                    'success': False,
                    'message': result.get('message', 'MoMo API error'),
                    'result_code': result.get('resultCode'),
                }

        except requests.exceptions.RequestException as e:
            _logger.error("=== create_momo_payment EXCEPTION === %s", str(e))
            transaction.write({'state': 'failed', 'message': str(e)})
            return {
                'success': False,
                'message': f"Connection error: {str(e)}",
            }

    @api.model
    def check_transaction_status(self, transaction_id):
        """Check the status of a MoMo transaction (called by POS polling)"""
        transaction = self.browse(transaction_id)
        if not transaction.exists():
            return {'state': 'failed', 'message': 'Transaction not found'}
        return {
            'state': transaction.state,
            'trans_id': transaction.trans_id or '',
            'message': transaction.message or '',
            'result_code': transaction.result_code,
        }
