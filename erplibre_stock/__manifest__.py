# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre stock',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'stock',
    'summary': 'INSTALL ERPLibre stock',
    'description': """
ERPLibre stock
===============

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        # odoo/addons
        'stock',
        'stock_account',
        'stock_dropshipping',
        'stock_landed_costs',
        'stock_picking_batch',
        # 'stock_zebra',

        # addons/Numigi_odoo-stock-addons
        'purchase_warehouse_access',
        'stock_component',
        'stock_component_account',
        'stock_inventory_accounting_date_editable',
        'stock_inventory_category_domain',
        'stock_inventory_internal_location',
        'stock_inventory_line_domain',
        'stock_inventory_line_domain_barcode',
        'stock_location_position_alphanum',
        'stock_picking_change_destination',
        'stock_serial_single_quant',
        'stock_theorical_quantity_access',
        'stock_turnover_rate',
        'stock_warehouse_access',
        'stock_warehouse_distance',

    ],
    'data': [],
    'installable': True,
}
