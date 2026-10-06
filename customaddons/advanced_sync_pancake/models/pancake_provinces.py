import json
import requests
import logging
from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class PancakeProvince(models.Model):
    _name = 'pancake.provinces'
    _description = 'Pancake Provinces'


    name = fields.Char(string='Tên tỉnh')
    api_province_id = fields.Char(string='ID tỉnh')
    country_code = fields.Char(string='Mã quốc gia')
    name_en = fields.Char(string='Tên tiếng Anh')
    new_id = fields.Char(string='Mã Tỉnh mới')
    region_type = fields.Selection([('north','Miền Bắc'), ('south','Miền Nam'), ('central','Miền Trung'), ('other', 'Khác')],string='Miền')
    is_new_province = fields.Boolean(string='Tỉnh mới?', default=False)
    pancake_districts_ids = fields.One2many('pancake.districts', string='Quận huyện', inverse_name='pancake_provinces_id')
    pancake_communes_ids = fields.One2many('pancake.communes', string='Phường xã', inverse_name='pancake_provinces_id')


