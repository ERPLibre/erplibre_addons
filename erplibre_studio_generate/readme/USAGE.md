1. Edit and **Apply** a project with the *ERPLibre studio* editor, then
   open it with **Project**.
2. Choose the destination and the version, then **Generate the module**;
   **Install the generated module** installs it in this database, once
   the module holds the last Apply. A module the project depends on (the
   module of another project whose models it extends) must be on the
   addons path of the server first.
3. After a new Apply, **Regenerate** writes the next version: the version
   of the project when it is above the last generated one, else the next
   patch version. Upgrade the module with the *Developer panel*.
4. The generation replaces only a folder this project generated in this
   database, recognised by its `.erplibre_studio` file. The technical name
   of the project no longer changes once a module is generated.
5. The name, summary and author of the project, the label and tooltip of
   its new fields and the label of its new models go into the Python code
   of the module: quotes, backslashes and line breaks are refused there.
6. A module with new models takes them over when it is installed in the
   database of its project: its `pre_init_hook` makes the custom models
   of the same names its own, so that their tables, records, views,
   menus, access rights and rules stay, updated in place. From then on
   the module owns them: a new label, chatter or default view waits for
   the next generation and upgrade, **Revert** is refused, and
   uninstalling the module deletes the models with their records.
   What Apply creates after a generation waits for the next one: an
   upgrade of the installed module keeps it, and each version ships the
   migration that takes over the models created since. A module older
   than its database refuses to load instead of deleting these models.
