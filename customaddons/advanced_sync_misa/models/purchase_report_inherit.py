from odoo import fields, models, api, _
import requests
import json
from odoo.exceptions import UserError
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from odoo.tools.query import Query
from odoo.tools.sql import SQL

# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.tools.sql import SQL


class PurchaseReport(models.Model):
    _inherit = "purchase.report"

    order_currency_id = fields.Many2one(
        'res.currency',
        string='Order Currency',
        readonly=True
    )

    order_currency_code = fields.Char(
        string='Order Currency Code',
        readonly=True
    )
    price_subtotal_original_currency = fields.Float(
        string="Untaxed Total (Original Currency)",
        readonly=True
    )
    price_total_original_currency = fields.Float(
        string="Total (Original Currency)",
        readonly=True
    )
    # ===== SQL =====
    def _select(self):
        return SQL(
            """
            %s,
            po.currency_id AS order_currency_id,
            rc.name AS order_currency_code,
            SUM(l.price_subtotal) AS price_subtotal_original_currency,
            SUM(l.price_total) AS price_total_original_currency
            """,
            super()._select()
        )

    def _from(self):
        return SQL(
            "%s LEFT JOIN res_currency rc ON rc.id = po.currency_id",
            super()._from()
        )

    def _group_by(self):
        return SQL(
            "%s, po.currency_id, rc.name",
            super()._group_by()
        )
