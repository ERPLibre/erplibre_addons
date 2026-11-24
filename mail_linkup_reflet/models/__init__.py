# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

# The mixins first: the models below inherit from them.
from . import contact_privacy  # isort: skip
from . import linkup_server_record  # isort: skip
from . import (
    discuss_channel,
    discuss_channel_member,
    discuss_channel_publish,
    discuss_channel_rtc_session,
    ir_ui_menu,
    linkup_block,
    linkup_category,
    linkup_email_blocklist,
    linkup_highlight,
    linkup_invitation,
    linkup_link,
    linkup_reflet,
    linkup_reflet_secret,
    linkup_report,
    mail_followers,
    mail_message,
    mail_notification,
    mail_thread,
    res_config_settings,
    res_partner,
    res_users,
    res_users_settings,
)
