{
    "name": "Code Generator Erplibre Devops",
    "category": "Uncategorized",
    "version": "12.0.1.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "application": True,
    "depends": [
        "code_generator",
        "code_generator_hook",
        "mail",
        "multi_step_wizard",
    ],
    "installable": True,
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
}
