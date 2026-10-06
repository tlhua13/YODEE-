# -*- coding: utf-8 -*-
{
    'name': "Advanced POS",

    'summary': """""",

    'description': """
    """,

    'author': "Magenest",
    'website': "https://magenest.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','point_of_sale','loyalty','pos_discount','product','advanced_sync_pancake'],

    # always loaded
    'data': [
        'data/cron.xml',
        'data/sequence.xml',

        # 'security/ir.model.access.csv',
        'views/res_company_inherit.xml',

        'views/loyalty_program_inherit.xml',
        'views/res_partner_inherit.xml',
        'views/sale_order_inherit.xml',
        'views/pos_order_inherit.xml',
        'views/loyalty_card_inherit.xml',
        'views/pos_order_line_inherit.xml',
        'report/detailed_sales_report_template.xml',
        'report/detailed_sales_report_action.xml',

    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'advanced_pos/static/src/**/*',
        ],
    },

}

