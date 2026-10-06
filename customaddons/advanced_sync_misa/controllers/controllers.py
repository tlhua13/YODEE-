# -*- coding: utf-8 -*-
import json
import math
import re
import traceback
from datetime import datetime, timedelta

import requests

from odoo import http

from odoo.http import request

VOUCHER_TYPE = [
    ('0', 'Chưa xác định'),
    ('1', 'Thu tiền gửi'),
    ('2', 'Chuyển tiền nội bộ'),
    ('3', 'Chi tiền gửi'),
    ('4', 'Phiếu chi'),
    ('5', 'Phiếu thu'),
    ('6', 'Chứng từ nghiệp vụ khác'),
    ('7', 'Nhập kho'),
    ('8', 'Xuất kho'),
    ('9', 'Chuyển kho'),
    ('10', 'Bán giảm giá'),
    ('11', 'Hóa đơn bán hàng'),
    ('12', 'Bán trả lại'),
    ('13', 'Bán hàng'),
    ('14', 'Mua giảm giá'),
    ('15', 'Hóa đơn mua hàng'),
    ('16', 'Mua trả lại'),
    ('17', 'Mua dịch vụ'),
    ('18', 'Mua hàng'),
    ('19', 'Kiểm kê kho'),
    ('20', 'Đơn đặt hàng'),
    ('21', 'Đơn mua hàng'),
]


class AdvancedSyncMisa(http.Controller):
    @http.route('/api/oauth/actopensupport/call_back_data', type="json", auth="public", website=False, method=['POST'], csrf=False)
    def callback_misa(self):
        try:
            success = True
            response = http.request.get_json_data()
            data = response
            signature = data['signature'] if 'signature' in data else None
            if data['success']:
                contents = json.loads(data['data'])
                for cont in contents:
                    org_refid = cont['org_refid']
                    success = cont['success']
                    error_message = cont['error_message']
                    session_id = cont['session_id']
                    voucher_type = cont['voucher_type'] if 'voucher_type' in cont else 0
                    transaction_type = str(voucher_type) if 0 <= int(voucher_type) <= 21 else '0'

                    data = {
                        "org_refid": org_refid,
                        "success": success,
                        "error_message": error_message,
                        "session_id": session_id,
                        "voucher_type": voucher_type,
                        "transaction_type": transaction_type,
                        "signature": signature
                    }
                    new_record = request.env['callback.misa'].sudo().create(data)

                    ### Link record đồng bộ
                    voucher_type = int(voucher_type)
                    if org_refid:
                        if 0 <= voucher_type <= 21:
                            # Đơn mua hàng
                            # Mua hàng dịch vụ
                            if voucher_type in [17, 21]:
                                data_ref = request.env['purchase.order'].sudo().search(['|', ('misa_id', '=', org_refid), ('misa_pu_invoice_id', '=', org_refid)])
                                if data_ref:
                                    data_ref.finish_sync_misa = True
                                    new_record.purchase_id = data_ref.id
                            # Đơn đặt hàng
                            if voucher_type in [13,20]:
                                data_ref = request.env['sale.order'].sudo().search([('misa_id', '=', org_refid)])
                                if data_ref:
                                    data_ref.finish_sync_misa = True
                                    new_record.sale_order_id = data_ref.id
                            # Nhập kho, Xuất kho, Chuyển kho, Mua hàng
                            if voucher_type in [7, 8, 9, 18]:
                                data_ref = request.env['stock.picking'].sudo().search([('misa_id', '=', org_refid)])
                                if data_ref:
                                    data_ref.finish_sync_misa = True
                                    new_record.picking_id = data_ref.id
                            # Kiểm kê kho
                            if voucher_type in [19]:
                                data_ref = request.env['stock.audit.misa'].sudo().search([('misa_id', '=', org_refid)])
                                if data_ref:
                                    data_ref.finish_sync_misa = True
                                    new_record.stock_audit_misa_id = data_ref.id

            if success:
                result = {
                    "Success": True,
                    "ErrorMessage": ""
                }
            else:
                # Nếu lỗi update sau
                result = {
                    "Success": False,
                    "ErrorCode": "InvalidParam",
                    "ErrorMessage": "Signature invalid"
                }

            result = json.dumps(result)

            IrLogging = request.env['ir.logging']
            message = ('response\n' + str(response) +
                       '\n\nresult\n' + str(result))
            IrLogging.sudo().create({'name': 'callback_misa',
                                     'type': 'server',
                                     'message': message,
                                     'path': '/api/oauth/actopensupport/call_back_data',
                                     'func': 'callback_misa',
                                     'line': 1})
            return result

        except Exception as e:
            error = traceback.format_exc()
            message = str(error)
            message += str(data)
            request.env['ir.logging'].sudo().create({
                'type': 'server',
                'name': 'callback_misa',
                'path': '/api/oauth/actopensupport/call_back_data',
                'line': 1,
                'func': 'Exception',
                'message': message
            })
            result = {
                "Success": False,
                "ErrorMessage": ""
            }
            result = json.dumps(result)
            return result
