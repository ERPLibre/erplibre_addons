1. Edit and **Apply** a project with the *ERPLibre studio* editor, then
   open it with **Project**.
2. Choose the destination and the version, then **Generate the module**;
   **Install the generated module** installs it in this database.
3. After a new Apply, **Regenerate** writes the next version: the version
   of the project when it is above the last generated one, else the next
   patch version. Upgrade the module with the *Developer panel*.
4. The generation replaces only a folder this project generated in this
   database, recognised by its `.erplibre_studio` file. The technical name
   of the project no longer changes once a module is generated.
5. The name, summary and author of the project, and the label and tooltip
   of its new fields, go into the Python code of the module: quotes,
   backslashes and line breaks are refused there.
