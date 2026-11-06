# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "LinkUp — Live chat",
    "summary": "Visitor welcome, reflection guide bot"
    " and moderator help in live chat",
    "version": "18.0.1.0.0",
    "author": "R. Michaud, S. Bassetto (Polytechnique Montréal, CIMAR LAB),"
    " Mathieu Benoit (TechnoLibre)",
    "website": "https://erplibre.ca",
    "category": "Productivity/Discuss",
    "license": "AGPL-3",
    "depends": [
        "mail_linkup_reflet",
        "im_livechat",
        "mail_linkup_community",
        "website_livechat",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/livechat_security.xml",
        "data/chatbot_script_data.xml",
        "data/im_livechat_channel_data.xml",
        "data/website_data.xml",
        "data/linkup_livechat_cron.xml",
    ],
    "assets": {
        # The widget of the visitors: the card, the form and the actions of
        # a reflection, and the guide, taken file by file from the web
        # client of the members, so that the views of a member (panel,
        # profile menu, first-use tour) and their stylesheets, which read
        # variables of the web client only, stay out of the public bundle.
        # The widget keeps the light theme (LU-NF-054): no *.dark.scss.
        "im_livechat.assets_embed_core": [
            "mail_linkup_reflet/static/src/core/common/category_picker.*",
            "mail_linkup_reflet/static/src/core/common/composer_patch.*",
            "mail_linkup_reflet/static/src/core/common/help_bar.*",
            "mail_linkup_reflet/static/src/core/common/linkup_category_icon.*",
            "mail_linkup_reflet/static/src/core/common/linkup_category_model.js",
            "mail_linkup_reflet/static/src/core/common/linkup_error_alert.*",
            "mail_linkup_reflet/static/src/core/common/linkup_errors.js",
            "mail_linkup_reflet/static/src/core/common/linkup_guide.js",
            "mail_linkup_reflet/static/src/core/common/linkup_guide.xml",
            "mail_linkup_reflet/static/src/core/common/linkup_read_watch.js",
            "mail_linkup_reflet/static/src/core/common/linkup_reflet_model.js",
            "mail_linkup_reflet/static/src/core/common/linkup_safety.*",
            "mail_linkup_reflet/static/src/core/common/linkup_signals.js",
            "mail_linkup_reflet/static/src/core/common/message_model_patch.js",
            "mail_linkup_reflet/static/src/core/common/message_patch.*",
            "mail_linkup_reflet/static/src/core/common/reflet_actions.*",
            "mail_linkup_reflet/static/src/core/common/reflet_card.*",
            "mail_linkup_reflet/static/src/core/common/reflet_composer.*",
            "mail_linkup_reflet/static/src/core/common/reflet_form.*",
            "mail_linkup_reflet/static/src/core/common/store_service_patch.js",
            "mail_linkup_reflet/static/src/core/common/thread_model_patch.js",
            "mail_linkup_community/static/src/core/common/linkup_help_now.*",
            "mail_linkup_community/static/src/core/common/"
            "linkup_moderation_texts.js",
            "im_livechat_linkup_reflect/static/src/common/**/*",
            "im_livechat_linkup_reflect/static/src/embed/**/*",
        ],
        "web.assets_backend": [
            "im_livechat_linkup_reflect/static/src/common/**/*",
            "im_livechat_linkup_reflect/static/src/core/**/*",
        ],
        "web.assets_unit_tests": [
            "im_livechat_linkup_reflect/static/tests/**/*",
            ("remove", "im_livechat_linkup_reflect/static/tests/embed/**/*"),
            ("remove", "im_livechat_linkup_reflect/static/tests/tours/**/*"),
        ],
        "im_livechat.embed_assets_unit_tests": [
            "im_livechat_linkup_reflect/static/tests/embed/**/*",
        ],
        "web.assets_tests": [
            "im_livechat_linkup_reflect/static/tests/tours/**/*",
        ],
    },
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
