import json
import requests
import logging
from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class PancakeCommunes(models.Model):
    _name = 'pancake.communes'
    _description = 'Pancake Communes'


    name = fields.Char(string='Tên phường/xã')
    api_district_id = fields.Char(string='ID quận huyện')
    api_province_id = fields.Char(string='ID tỉnh')
    api_communes_id = fields.Char(string='ID phường xã')
    postcode = fields.Char(string='Mã bưu điện')
    name_en = fields.Char(string='Tên tiếng anh')
    new_id = fields.Char(string='Mã phường xã mới')
    region_type = fields.Char()
    is_communes_new = fields.Boolean(string='Phường xã mới?')
    pancake_district_id = fields.Many2one('pancake.districts', string='Quận huyện')
    pancake_provinces_id = fields.Many2one('pancake.provinces', string='Tỉnh/TP')
