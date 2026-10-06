import json
import requests
import logging
from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class PancakeDistricts(models.Model):
    _name = 'pancake.districts'
    _description = 'Pancake Districts'


    name = fields.Char(string='Tên quận huyện')
    api_district_id = fields.Char(string='ID huyện')
    api_province_id = fields.Char(string='ID tỉnh')
    postcode = fields.Char(string='Mã bưu điện')
    name_en = fields.Char(string='Tên tiếng Anh')
    new_id = fields.Char(string='Mã quận huyện mới')
    region_type = fields.Char()
    is_new_district = fields.Boolean(string='Quận huyện mới?')
    pancake_provinces_id = fields.Many2one('pancake.provinces', string='Tỉnh/TP')
    pancake_communes_ids = fields.One2many('pancake.communes', string='Phường xã', inverse_name='pancake_district_id')
