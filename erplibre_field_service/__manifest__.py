# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre field_service',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'field_service',
    'summary': 'INSTALL ERPLibre field_service',
    'description': """
ERPLibre field_service
=============================

""",
    'depends': [
        # addons/ERPLibre_erplibre_addons
        'erplibre_base',
        'erplibre_base_quebec',

        # addons/OCA_field-service
        'fieldservice',
        'fieldservice_account',
        'fieldservice_account_analytic',
        'fieldservice_account_payment',
        'fieldservice_activity',
        'fieldservice_agreement',
        'fieldservice_change_management',
        'fieldservice_crm',
        'fieldservice_delivery',
        'fieldservice_distribution',
        'fieldservice_fleet',
        'fieldservice_geoengine',
        # 'fieldservice_google_map',
        # 'fieldservice_google_marker_icon_picker',
        'fieldservice_isp_account',
        'fieldservice_isp_flow',
        'fieldservice_location_builder',
        'fieldservice_maintenance',
        'fieldservice_partner_multi_relation',
        'fieldservice_project',
        'fieldservice_purchase',
        'fieldservice_recurring',
        'fieldservice_repair',
        'fieldservice_route',
        'fieldservice_route_account',
        'fieldservice_route_stock',
        'fieldservice_route_vehicle',
        'fieldservice_sale',
        'fieldservice_sale_recurring',
        'fieldservice_sale_stock',
        'fieldservice_size',
        'fieldservice_skill',
        'fieldservice_stage_server_action',
        'fieldservice_stage_validation',
        'fieldservice_stock',
        'fieldservice_stock_account',
        'fieldservice_stock_account_analytic',
        'fieldservice_substatus',
        'fieldservice_vehicle',
        'fieldservice_vehicle_stock',

    ],
    'data': [],
    'installable': True,
}
