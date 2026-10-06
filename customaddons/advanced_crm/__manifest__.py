# -*- coding: utf-8 -*-
{
    'name': "Advanced CRM",

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
    'depends': ['base','crm','sale','advanced_sync_pancake','advanced_sync_misa'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',
        'views/crm_stage_view_inherit.xml',
        'views/crm_lead_view_inherit.xml',
        'views/crm_team_view_inherit.xml',
        'views/product_pricelist_view_inherit.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'views/crm_stage_view_inherit.xml',
    ],
}

