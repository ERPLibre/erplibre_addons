# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre wiki',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'Base',
    'summary': 'INSTALL ERPLibre wiki',
    'description': """
ERPLibre wiki
=====================

""",
    'depends': [
        # Custom ERPLibre
        # addons/ERPLibre_erplibre_addons
        'erplibre_base',

        # addons/OCA_knowledge
        'attachment_preview',
        'document_page',
        'document_page_approval',
        'document_page_group',
        'document_page_project',
        'document_page_reference',
        'document_page_tag',
        'document_url',
        'knowledge',

        # addons/OCA_management-system
        'document_page_procedure',
        'document_page_quality_manual',
        'document_page_work_instruction',
        'mgmtsystem',
        'mgmtsystem_action',
        'mgmtsystem_audit',
        'mgmtsystem_hazard',
        'mgmtsystem_manual',
        'mgmtsystem_nonconformity',
        'mgmtsystem_nonconformity_hr',
        'mgmtsystem_nonconformity_product',
        'mgmtsystem_nonconformity_project',
        'mgmtsystem_quality',
        'mgmtsystem_review',
        'mgmtsystem_survey',

    ],
    'data': [],
    'installable': True,
}
