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
7. Once the module is installed, the menu of each app shows the icon of
   the module, the copy made at the generation: **Apply** keeps it, and a
   new icon chosen for an app waits for the next generation and upgrade;
   an app the installed module does not hold yet keeps its chosen icon
   until then, and **Apply** says it waits.
8. Each record rule and each group of the module holds its whole state
   (the groups of a rule, empty for a global one, its four permissions,
   the comment of a group, empty included): an upgrade writes only what a
   record names. The generation checks the groups and the rules again, as
   Apply does: a group of the project never implies a group that grants
   the Settings, and an existing group goes into the module by its
   external id under an installed module.
9. Uninstalling the generated module deletes its models with their
   records, its fields, menus, access rights, rules and groups; the
   uninstall wizard lists them and asks to confirm (*ERPLibre studio*).
   In the database of its project, the project is back to a draft with
   its lines, and its next generation starts from a new **Apply**.
