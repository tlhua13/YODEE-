import json
import traceback
import urllib.parse

from odoo import models, fields, api

class YodeeIrLogging(models.Model):
    _name = 'yodee.ir.logging'
    _description = 'Yodee Logging with JSON Export'

    name = fields.Char(string='Name')

    # Request
    request_method = fields.Char()
    request_url = fields.Char()
    request_header = fields.Char()
    request_body = fields.Char()
    request_body_formated = fields.Text(compute='_compute_request_body_formated', store=True)
    request_form = fields.Char()
    request_cookies = fields.Char()

    # Response
    response_status = fields.Integer()
    response_header = fields.Char()
    response_cookies = fields.Char()
    response_body = fields.Char()
    response_body_formated = fields.Text(compute='_compute_response_body_formated', store=True)
    python_exception = fields.Char()
    python_traceback = fields.Text()
    type = fields.Selection([
        ('import', 'Import API call'),
        ('export', 'Export API call'),
    ], compute='_compute_type', store=True)
    source = fields.Selection([('odoo', 'Odoo'), ('m2', 'M2'),('pancake', 'Pancake')], string='Source', default='pancake')

    token = fields.Char(compute='_compute_token')
    curl = fields.Text(compute='_compute_curl')

    @api.depends('request_body')
    def _compute_type(self):
        for rec in self:
            rec.type = 'export' if rec.request_body else 'import'

    @api.depends('request_cookies', 'request_header')
    def _compute_token(self):
        for rec in self:
            token = ''
            if rec.request_header:
                headers = json.loads(rec.request_header)
                token = headers.get('Authorization') or headers.get('HTTP_AUTHORIZATION')
            rec.token = token

    @api.depends('request_url', 'request_header', 'request_body')
    def _compute_curl(self):
        for rec in self:
            curl_parts = []

            if rec.request_url:
                curl_parts.append(f"curl --location --request {rec.request_method} '{rec.request_url}'")
                curl_parts.append("--header 'Content-Type: application/json'")

            if rec.token:
                curl_parts.append(f"--header 'Authorization: {rec.token}'")

            if rec.request_body:
                curl_parts.append(f"--data-raw '{rec.request_body}'")

            rec.curl = " \\\n".join(curl_parts)

    @api.depends('request_body')
    def _compute_request_body_formated(self):
        for record in self:
            try:
                record.request_body_formated = json.dumps(json.loads(record.request_body), indent=4) if record.request_body else None
            except Exception:
                record.request_body_formated = record.request_body

    @api.depends('response_body')
    def _compute_response_body_formated(self):
        for record in self:
            try:
                record.response_body_formated = json.dumps(json.loads(record.response_body), indent=4) if record.response_body else None
            except Exception:
                record.response_body_formated = record.response_body

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        for rec in res:
            rec.name = self.env['ir.sequence'].next_by_code('yodee.log')
            rec.request_body = rec.request_body.replace("'", '"') if rec.request_body else None
            rec.response_body = rec.response_body.replace("'", '"') if rec.response_body else None
        return res

    def log_outgoing_request(self, response=None, data=None, source=None):
        try:
            api_log_val = {
                'request_method': response.request.method,
                'request_url': urllib.parse.unquote(response.url).replace('+', ' '),
                'request_header': json.dumps(dict(response.request.headers)),

                'response_status': response.status_code,
                'response_header': response.headers,
                'response_cookies': json.dumps(dict(response.cookies)),
                'python_traceback': '\n'.join(traceback.format_stack()),
            }
            api_log_val['request_body'] = json.loads(json.dumps(data)) if data else None
            api_log_val['response_body'] = json.loads(json.dumps(response.text)) if response.text else None
            return self.sudo().create(api_log_val)
        except Exception as e:
            self.env['ir.logging'].sudo().create({
                'type': 'server',
                'name': 'log_outgoing_request Exception',
                'path': 'customaddons/amirim/models/amirim/amirim_api_log.py',
                'line': 'line',
                'func': 'log_outgoing_request',
                'message': str(e)
            })

    @api.model
    def log_incoming_request(self, request=None, data=None,source=None, status=200):
        try:
            api_log_val = {
                'name': request.url or '',
                'python_traceback': '\n'.join(traceback.format_stack()),

                # Request
                'request_method': request.method,
                'request_url': request.url,
                'request_header': json.dumps(dict(request.headers.environ)),
                'request_cookies': json.dumps(dict(request.cookies)),

                # Response
                'response_body': data,
                'response_status': status,
                'source': source,
            }
            api_log_val['request_body'] = json.dumps(json.loads(request.data)) if request.data else None
            self.sudo().create(api_log_val)
        except Exception as e:
            self.env['ir.logging'].sudo().create({
                'type': 'server',
                'name': 'log_incoming_request Exception',
                'path': 'customaddons/amirim/models/amirim/amirim_api_log.py',
                'line': 'line',
                'func': 'log_incoming_request',
                'message': str(e)
            })

