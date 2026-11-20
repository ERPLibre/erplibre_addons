The checkout is the one above the running Odoo that holds
`conf/module_list_image_db_odoo.json`. The system parameter
`erplibre_info.root`, shared with *ERPLibre info*, names another
directory.

The daily analysis is the scheduled action *ERPLibre: doctor*, active
at installation; its hour is the one of its next execution date. The day
of its report name is the one of the company's time zone, else of the
administrator's. The
users to notify are kept in the system parameter
`erplibre_doctor.notify_user_ids`, their ids separated by commas.

A suggested module the report finds « Not found » is not in the module
list: *Apps › Update Apps List* reads the addons path again.
