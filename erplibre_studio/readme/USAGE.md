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
   goes: a new app, named and with the icon of an installed module, or
   under an existing menu. The model waits for **Apply**; **Apply and
   open** creates it and edits its form, and its **Form**, **List** and
   **Search** buttons edit its views as any other view. The project form
   holds the same lines, page **New models**.
5. **Access rights** shows, instead of the view, the rights of the groups
   on the models of the project and on the existing models it names,
   next to the rights the other modules give on them: each checkbox is a
   change of the draft. **Record rules** lists the rules of the project;
   **Check** evaluates the domain of a rule as Odoo does, and counts the
   records it matches once the model exists. The project form has the
   pages **Access rights** and **Record rules** too. A new model needs at
   least one access right. The rights, the users, the companies, the
   settings and the technical models (`ir.*`) take no right nor rule
   from a project; on an existing model, the portal and public groups
   may only read, and take no record rule: Odoo adds up the rules of the
   groups of a user, so such a rule would widen what they reach.
6. **Preview** shows the view as it will be, with a placeholder for the
   new fields not created yet.
7. **Apply** writes the fields and the views into the database: every user
   sees them.
8. **Project** opens the project: its changes, and the fields and views
   it put in the database. **Revert** removes them from the database,
   with the records of its models; the changes and the lines stay, as a
   draft, but for the changes of the default views of its models, which
   go with these views. Apply and Revert refuse to remove a field, a
   model or a menu that something else still uses: a record rule whose
   domain names the field, a change of another project, an access right
   or a rule of another project on the model. **Discard** goes back to
   the last Apply, without the lines whose model, menu, group or view
   left the database since, and says which. With *ERPLibre studio
   generate*, the project form also writes the project as a module.
9. Once a module generated from the project is installed, it owns its
   fields and models: a new label, tooltip or selection of such a field,
   a new label or chatter of such a model, takes effect with the next
   generation and upgrade of the module, and **Apply** says so. **Revert**
   is refused until the module is uninstalled.
10. Uninstalling *ERPLibre studio* is refused while a project has records
    in the database and its generated module is not installed: revert
    the projects first, or install their modules.
