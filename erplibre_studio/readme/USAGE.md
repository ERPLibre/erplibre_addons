1. Activate the developer mode, open a form or a list, open the debug
   menu (the bug icon) and choose **Customize this view**.
2. Choose a project, or create one: a name and the technical name of the
   module it generates.
3. Drag a field to move it; drag a field type or an existing field from
   the left onto a drop zone to add it. Click a field to edit its
   properties on the right. **Undo** removes the last change of the view.
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
