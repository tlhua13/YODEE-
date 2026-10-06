import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError

_logger = logging.getLogger(__name__)


class MsOfficeController(http.Controller):

    @http.route('/ms_office/download/<int:attachment_id>', auth='public', methods=['GET'], csrf=False)
    def ms_office_download_attachment(self, attachment_id, **kwargs):
        """
        Public route to download attachments using superuser call to web/content
        URL: /ms_office/download/<attachment_id>
        """
        try:
            attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
            if not attachment.exists():
                return request.not_found()

            from odoo.addons.web.controllers.binary import Binary

            request.env = request.env(su=True)
            binary_controller = Binary()
            return binary_controller.content_common(
                xmlid=None,
                model='ir.attachment',
                id=attachment_id,
                field='datas',
                filename_field='name',
                mimetype=attachment.mimetype,
                download=True,
                **kwargs
            )
        except (AccessError, MissingError) as e:
            _logger.warning("Access denied for attachment %s: %s", attachment_id, e)
            return request.render('http_routing.403')
        except Exception as e:
            _logger.error("Error downloading attachment %s: %s", attachment_id, e)
            return request.render('http_routing.500')
