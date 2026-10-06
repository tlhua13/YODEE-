# -*- coding: utf-8 -*-
{
    'name': "Advanced Sync Pancake",

    'summary': "advanced_sync_pancake",

    'description': """""",

    'author': "Magenest",
    'website': "https://www.yourcompany.com",

    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base','sale','product','sale_management','mail','contacts','stock','hr','account','purchase'],

    'data': [
        'security/ir.model.access.csv',

        'data/sequence.xml',
        'data/pancake_connector_data.xml',
        'data/cron.xml',
        'data/product_data.xml',

        # 'views/yodee_ir_logging.xml',
        'views/yodee_api_log_view.xml',
        'views/pancake_order_webhook_views.xml',

        # 'views/sync_pancake_settings.xml',

        'views/pancake_product_template.xml',
        'views/pancake_shop.xml',
        'views/product_template_inherit.xml',
        'views/pancake_connector_views.xml',
        'views/pancake_provinces_views.xml',
        'views/pancake_districts_views.xml',
        'views/pancake_communes_views.xml',
        'views/pancake_warehouse_views.xml',
        'views/pancake_order_source_view.xml',
        'views/pancake_branch_views.xml',

        'views/stock_location_inherit.xml',
        'views/stock_picking.xml',

        'views/res_partner_inherit_view.xml',

        'views/sale_order_views.xml',
        'views/sale_order_line.xml',

        'views/sale_area.xml',
        'views/stock_quant_inherit_views.xml',
        'wizard/product_change_uom_view.xml',


    ],
    'assets': {
        'web.assets_backend': [
            'advanced_sync_pancake/static/src/js/attachment_list.js',
            'advanced_sync_pancake/static/src/xml/attachment_list.xml',
        ],
    },

}

