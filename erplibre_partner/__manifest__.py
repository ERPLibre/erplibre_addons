# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre partner',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'partner',
    'summary': 'INSTALL ERPLibre partner',
    'description': """
ERPLibre partner
=================

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        'res_partner_fix_group_by_company',
        'contacts',
        'partner_no_vat',

        # addons/Numigi_odoo-partner-addons
        'contacts_config_menu_moved_right',
        'contacts_config_sale_manager',
        'google_partner_address',
        'partner_autocomplete_disable',
        'partner_change_parent',
        'partner_change_parent_affiliate',
        'partner_contact_type_visible',
        # 'partner_duplicate_mgmt',   depend de unidecode
        'partner_duplicate_multi_phone',
        'partner_duplicate_multi_relation',
        'partner_edit_group',
        'partner_firstname_before_lastname',
        'partner_gst_qst',
        'partner_key_date',
        'partner_multi_phone',
        'partner_multi_relation_note',
        'partner_multi_relation_strength',
        'partner_multi_relation_work',
        'partner_name_no_shortcut',
        'partner_no_vat',
        'partner_no_vat_website_sale',
        'partner_phone_no_envelope',
        'partner_phone_validation',
        'partner_reference',
        'partner_unique_email',
        'partner_website_domain_only',
        'res_partner_bank_shared_account',

    ],
    'data': [],
    'installable': True,
}