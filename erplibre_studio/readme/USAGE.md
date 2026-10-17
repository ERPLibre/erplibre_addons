1. Activate the developer mode, open a view, open the debug
   menu (the bug icon) and choose **Customize this view**, or
   **Customize the search view** for the search view of the page.
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
4. **Preview** shows the view as it will be, with a placeholder for the
   new fields not created yet.
5. **Apply** writes the fields and the views into the database: every user
   sees them.
6. **Project** opens the project: its changes, and the fields and views
   it put in the database. **Revert** removes them from the database;
   the changes stay, as a draft. With *ERPLibre studio generate*, the
   project form also writes the project as a module.
7. Once a module generated from the project is installed, it owns its
   fields: a new label, tooltip or selection of such a field takes effect
   with the next generation and upgrade of the module, and **Apply** says
   so.
