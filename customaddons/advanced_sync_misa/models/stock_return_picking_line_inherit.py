import pytz

from odoo import api, fields, models, _
import requests
import json
from odoo.exceptions import UserError
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from odoo import api, fields, models
class StockReturnPickingLineInherit(models.TransientModel):
    _inherit = 'stock.return.picking.line'

    product_status = fields.Boolean(
        related='product_id.active',
        string="Product Status"
    )
