1. Activate the developer mode, open a view, open the debug
   menu (the bug icon) and choose **Customize this view**, or
   **Customize the search view** for the search view of the page. On a
   model a project creates, the editor opens that project.
2. Choose a project, or create one: a name and the technical name of the
   module it generates.
3. Drag a field to move it; drag a field type or an existing field from
   the left onto a drop zone to add it. Click a field to edit its
   properties on the right. **Undo** removes the last change of the view.
   In a search view, **New filter** builds a filter from a field, an
   operator and a value; the interval of the palette applies to a date
   field dropped on the group-by column or on a pivot axis. In a pivot
   view, drop a field on the rows, the columns or the measures. A drop
   zone never splits a `t-if` / `t-else` pair of a kanban card. With no
   node selected, the side panel sets the options of the view.
4. **New model**, in the toolbar of the editor or in the side panel,
   asks a label, a technical name (`x_`, set from the label until
   edited), the chatter (when *Discuss* is installed), and where its menu
   goes: an app of the project, or a new one named and with the icon of
   an installed module, or under an existing menu. The model waits for
   **Apply**; its **Form**, **List** and **Search** buttons edit its
   views before it exists (fields, moves, labels; filters and group-by
   wait for Apply), **Apply and open** creates it and edits its form. The
   project form holds the same lines, pages **New models** and **Apps and
   groups**.
5. **Access rights** shows, instead of the view, the rights of the groups
   on the models of the project and on the existing models it names,
   next to the rights the other modules give on them: each checkbox is a
   change of the draft. **Record rules** lists the rules of the project;
   **Check** evaluates the domain of a rule as Odoo does, and counts the
   records it matches once the model exists. The project form has the
   pages **Access rights** and **Record rules** too. A new model needs at
   least one access right. A rule without a group applies only once
   **Global** is checked, which only a rule on a model of the project can
   be: a global rule restricts every user, the Settings users included;
   Apply names the rule otherwise. A group that left the database since
   it was chosen is flagged on the rule, and Apply waits for the groups
   to be chosen again. An existing group is named by its external id
   under an installed module (never one under `__export__`). The rights,
   the users, the companies, the settings, the technical models (`ir.*`)
   and the ERPLibre models (`erplibre.*`) take no right nor rule from a
   project; on an existing model, the portal and public groups
   may only read, and take no record rule: Odoo adds up the rules of the
   groups of a user, so such a rule would widen what they reach.
6. **Preview** shows the view as it will be, with a placeholder for the
   new fields not created yet. On a model not created yet, the preview is
   a **simulation**: nothing is written. **Approve for a real preview**
   records who approved what; the **real** preview then creates the
   models in a savepoint, renders them, and rolls back. While it renders
   (a second at most, then the lock and statement timeouts end it), the
   writers of the users table and of the tables the new models point to
   wait: approve it on a production database knowingly. Any change of
   these models withdraws the approval, and so do Apply and Revert. In
   the simulation, the fields of the models of the database neither open
   nor create a record, and a dialog opened from the preview saves
   nothing either. The preview follows the draft: it is shown again
   after Undo or a change, and closed once Apply created its model.
7. **Apps and groups**, in the toolbar of the editor or on the project
   form: an app is a top-level menu, with its icon, and the category of
   its groups. A group of the project implies groups of the project (each
   one the previous, to show as one selection in the user form) and
   existing groups (the internal users by default; never the Settings,
   nor a group that grants them, nor the portal or public groups). The
   access grid and the rules offer the groups of the project after the
   existing ones. A group of the project a group no longer implies is
   taken, at Apply, from the members who had it only through that
   implication; Apply lists them first.
8. **New field** one2many, dropped into a form: choose the comodel, then
   an inverse many2one, or let the studio create it on the comodel; the
   form shows it as a sub-list. Many2many, dropped into a form (a
   sub-list), a list or a kanban (tags): the relation table and its
   columns are named by the server, after the module.
9. **Apply** writes the fields and the views into the database: every user
   sees them. When it removes records, values or group members, it lists
   them first and asks to confirm.
10. **Project** opens the project: its changes, and the fields and views
   it put in the database. **Revert**, in the toolbar of the editor or on
   the project form, removes them from the database,
   with the records of its models and their filters, after a list of
   what leaves the database; the changes and the lines stay, as a draft,
   but for the changes of the default views of its models, which go with
   these views. When what leaves changed since the list was shown, the
   confirmation shows it again before it confirms. Apply and Revert
   refuse to remove a field, a model or a menu that something else still
   uses: a record rule whose domain names the field, a change of another
   project, an access right or a rule of another project on the model, a
   server or scheduled action, an e-mail template or a default value made
   by hand on it. Undo, or removing a one2many whose inverse the studio
   creates, takes with it the changes that show that inverse. **Discard** goes back to
   the last Apply, without the lines whose model, menu, group or view
   left the database since, and says which. With *ERPLibre studio
   generate*, the project form also writes the project as a module.
11. Once a module generated from the project is installed, it owns its
   fields and models: a new label, tooltip or selection of such a field,
   a new label or chatter of such a model, takes effect with the next
   generation and upgrade of the module, and **Apply** says so. **Revert**
   is refused until the module is uninstalled, whatever the project
   applied (models, groups, rights).
12. Uninstalling a module generated from a project, from the Apps, shows
    what it deletes (its models with their records, its fields with their
    values, menus, rights, rules, groups with their members, and what the
    database deletes with its models: the fields and rights of other
    projects or modules on them) and asks « I understand » first. It is
    refused while another project applied fields, rights, rules or views
    on these models: revert them first. The project is then a draft
    again, with its lines.
13. Uninstalling *ERPLibre studio* is refused while a project has records
    in the database and its generated module is not installed: revert
    the projects first, or install their modules.
