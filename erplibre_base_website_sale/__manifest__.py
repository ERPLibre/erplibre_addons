# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).



{
    'name': 'ERPLibre website sale',
    'version': '0.2',
    'author': "ERPLibre",
    'website': 'https://erplibre.ca',
    'license': 'AGPL-3',
    'category': 'Sales',
    'summary': 'INSTALL ERPLibre website sale',
    'description': """
ERPLibre Website Sale
===============

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        # OCA_ecommerce
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
        #'website_sale_product_brand',
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
        #'website_sale_tax_toggle',
        #'website_sale_vat_required',
        'website_sale_wishlist_keep',
        'website_snippet_carousel_product',
        'website_snippet_product_category',
        'website_snippet_product_category',
        # TODO products comment and reviews by users on site
        'product_rating_review',


    ],
    'data': [],
    'installable': True,
}
