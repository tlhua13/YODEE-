# -*- coding: utf-8 -*-
{
    'name': "Advanced Sync Misa",

    'summary': """""",

    'description': """
    """,

    'author': "Magenest",
    'website': "https://magenest.com",

    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'sale_management', 'purchase', 'purchase_stock', 'product',
                'contacts', 'hr', 'account', 'stock', 'uom',
                'purchase_stock', 'advanced_sync_pancake','sales_team'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',

        'data/cron.xml',
        'data/parameter.xml',
        'data/partner_data.xml',
        'data/report_saleorder_document_inherit.xml',
        'data/report_delivery_document_inherit.xml',

        'views/misa_menu_root.xml',

        'views/callback_misa.xml',

        'views/res_config_settings.xml',
        'views/res_partner_inherit.xml',

        'views/hr_employee_inherit.xml',

        'views/product_category_misa.xml',
        'views/product_template_inherit.xml',

        'views/stock_location_misa.xml',
        'views/stock_audit_misa.xml',
        'views/stock_location_inherit.xml',
        'views/stock_quant_inherit.xml',
        'views/stock_picking_type_inherit.xml',
        'views/stock_picking_view_inherit.xml',

        'views/account_payment_term_inherit.xml',
        'views/account_account_misa.xml',
        'views/account_payment_term_misa.xml',

        'views/uom_uom_inherit.xml',

        'views/sale_order_inherit.xml',
        'views/yodee_discount_type_views.xml',
        'views/sale_order_discount_views.xml',
        'views/stock_return_picking_inherit_view.xml',

        'views/purchase_order_inherit.xml',

        'views/pancake_order_source_inherit.xml',
        'views/sale_order_detail_inherit_views.xml',
        'views/stock_move_line_inherit_view.xml',
        'views/product_supplierinfo_inherit.xml',
        'wizard/popup_tax_update_view.xml',
        'wizard/popup_misa_features_update_view.xml',
        'wizard/popup_sync_dictionary.xml',
        'views/product_product_inherit.xml',
        'wizard/import_product_uom_view.xml',
        'wizard/import_sale_order_update_view.xml',
    ],
}
