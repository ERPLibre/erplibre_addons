# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre e-commerce',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'e-commerce',
    'summary': 'INSTALL ERPLibre e-commerce',
    'description': """
ERPLibre e-commerce
====================

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        # odoo/addons
        'website_sale',
        'website_sale_comparison',
        'website_sale_delivery',
        'website_sale_digital',
        'website_sale_link_tracker',
        'website_sale_management',
        'website_sale_stock',
        'website_sale_wishlist',

        # addons/OCA_ecommerce
        'website_sale_attribute_filter_category',
        'website_sale_attribute_filter_order',
        'website_sale_attribute_filter_price',
        'website_sale_cart_selectable',
        'website_sale_category_description',
        'website_sale_checkout_country_vat',
        'website_sale_checkout_skip_payment',
        'website_sale_exception',
        'website_sale_hide_empty_category',
        'website_sale_hide_price',
        'website_sale_product_attachment',
        'website_sale_product_attribute_filter_visibility',
        'website_sale_product_attribute_value_filter_existing',
        # 'website_sale_product_brand',
        'website_sale_product_detail_attribute_image',
        'website_sale_product_detail_attribute_value_image',
        'website_sale_product_minimal_price',
        'website_sale_product_reference_displayed',
        'website_sale_product_sort',
        'website_sale_product_style_badge',
        'website_sale_require_legal',
        'website_sale_require_login',
        'website_sale_secondary_unit',
        'website_sale_show_company_data',
        'website_sale_stock_available',
        'website_sale_stock_available_display',
        'website_sale_stock_force_block',
        'website_sale_suggest_create_account',
        # 'website_sale_tax_toggle',
        # 'website_sale_vat_required',
        'website_sale_wishlist_keep',
        'website_snippet_carousel_product',
        'website_snippet_product_category',
        'website_snippet_product_category',

        # addons/odooaktiv_product_rating_app
        'product_rating_review',

        # addons/pledra_odoo-product-configurator
        'product_configurator',
        'product_configurator_mrp',
        'product_configurator_purchase',
        'product_configurator_sale',
        # 'product_configurator_sale_mrp',
        'product_configurator_stock',
        # 'product_configurator_stock_lots',
        # 'product_configurator_subconfig',
        'website_product_configurator',
        # 'website_product_configurator_mrp',

    ],
    'data': [],
    'installable': True,
}
