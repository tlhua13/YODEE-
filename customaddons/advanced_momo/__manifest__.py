# -*- coding: utf-8 -*-
{
    'name': "Advanced Momo",

    'summary': """MoMo QR Payment integration for POS""",

    'description': """
        Integrate MoMo e-wallet QR payment into Odoo POS.
        - Show MoMo QR code in POS payment screen
        - Auto-detect payment via webhook (IPN)
        - Configure MoMo credentials in Settings or per Payment Method
    """,

    'author': "Magenest",
    'website': "https://magenest.com",

    'category': 'Point of Sale',
    'version': '0.2',

    'depends': ['base', 'point_of_sale', 'loyalty'],

    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'report/momo_qr_report_action.xml',
        'report/momo_qr_report_template.xml',
        'views/loyalty_program_inherit.xml',
        'views/pos_payment_method_views.xml',
        'views/res_config_settings_views.xml',
        'views/momo_transaction_views.xml',
        'views/pos_order_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'advanced_momo/static/src/app/momo_payment.js',
            'advanced_momo/static/src/app/momo_qr_display.js',
            'advanced_momo/static/src/app/momo_qr_display.xml',
            'advanced_momo/static/src/app/payment_screen_inherit.js',
            'advanced_momo/static/src/app/payment_screen_inherit.xml',
        ],
    },
}
