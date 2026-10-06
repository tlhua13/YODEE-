# -*- coding: utf-8 -*-
from odoo.addons.web.controllers.home import Home
import werkzeug
from odoo import http
from odoo.http import request
# import random
# Todo su dung de tao token ngau nhien khi doi mat khau cho nguoi dung
# def random_token():
#     # the token has an entropy of about 120 bits (6 bits/char * 20 chars)
#     chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
#     return ''.join(random.SystemRandom().choice(chars) for _ in range(20))

class HomeController(Home):
    def _web_client_readonly(self):
        return False
    @http.route(['/web', '/odoo', '/odoo/<path:subpath>', '/scoped_app/<path:subpath>'], type='http', auth="none",
                readonly=_web_client_readonly)
    def web_client(self, s_action=None, **kw):
        try:
            if request.session.uid:
                # Todo su dung de chuyen huong nguoi dung toi trang reset password
                # Todo (NOTE): Token này vẫn lưu trong cache của trình duyệt, khi delete history thì mới mất
                # if request.session.get('first_login'):
                #     user = request.env['res.users'].sudo().browse(request.session.uid)
                #     token = random_token()
                #     user.partner_id.sudo().write({'signup_token': token})
                #     url = f'/web/reset_password?db={request.session.db}&token={token}'
                #     return request.redirect(url)
                if 'debug=' in request.httprequest.full_path:
                    debug_position = request.httprequest.full_path.index('debug=')
                    if request.httprequest.full_path[debug_position + 6] != '#':
                        if not request.env.ref('base.group_system').id in request.env['res.users'].sudo().browse(
                                request.session.uid).groups_id.ids:
                            return werkzeug.utils.redirect('/web?debug=', 303)
        except Exception as ex:
            a = 0
        return super(HomeController, self).web_client(kw)