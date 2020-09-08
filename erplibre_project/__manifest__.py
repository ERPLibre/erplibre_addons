# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre project',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'project',
    'summary': 'INSTALL ERPLibre project',
    'description': """
ERPLibre project
=================

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        # odoo/addons
        'project',

        # addons/Numigi_odoo-project-addons
        'project_chatter',
        'project_default_task_stage',
        'project_form_with_dates',
        'project_hide_create_sale_order',
        'project_iteration',
        'project_iteration_parent_only',
        'project_iteration_parent_type_required',
        'project_portal_hide_timesheets',
        'project_portal_parent_task',
        'project_remaining_hours_update',
        'project_stage',
        'project_stage_allow_timesheet',
        'project_stage_no_quick_create',
        'project_task_date_planned',
        'project_task_deadline_from_project',
        'project_task_full_text_search',
        'project_task_id_in_display_name',
        'project_task_link',
        'project_task_reference',
        'project_task_resource_type',
        'project_task_search_parent_subtask',
        'project_task_stage_external_mail',
        'project_task_subtask_same_project',
        'project_task_subtask_time_range',
        'project_task_time_range',
        'project_task_type',
        'project_template',
        'project_template_timesheet',
        'project_time_management',
        'project_time_range',
        'project_type',
        
        # Scrummer
        'project_agile_sale_timesheet',
        'scrummer',
        'scrummer_kanban',
        'scrummer_scrum',
        'scrummer_workflow_security',
        'scrummer_workflow_transition_by_project',
        'scrummer_workflow_transitions_by_task_type',
    ],
    'data': [],
    'installable': True,
}
