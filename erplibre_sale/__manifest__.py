# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre sale',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'sale',
    'summary': 'INSTALL ERPLibre sale',
    'description': """
ERPLibre sale
==============

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',
        'sale_order_line_limit',
        'sale_degroup_tax',
        'payment',
        'payment_transfer',
        'purchase',
        'stock',

        # odoo/addons
        'sale',
        'sale_crm',
        'sale_expense',
        'sale_management',
        'sale_margin',
        'sale_mrp',
        'sale_purchase',
        'sale_quotation_builder',
        'sale_stock',
        'sale_timesheet',
        'sales_team',

        # addons/Numigi_odoo-product-addons
        'product_create_group',
        'product_dimension',
        'product_extra_views',
        'product_extra_views_purchase',
        'product_extra_views_sale',
        'product_extra_views_stock',
        'product_kit',
        'product_panel_shortcut',
        'product_reference',
        'product_reference_list_view',
        'product_supplier_name_search',
        'product_variant_button_complete_form',
    ],
    'data': [],
    'installable': True,
}
