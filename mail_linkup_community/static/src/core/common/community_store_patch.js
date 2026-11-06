import {Store} from "@mail/core/common/store_service";

import {patch} from "@web/core/utils/patch";

// Set by `res.users._init_store_data` of this module for a LinkUp member,
// and on the bus when the address is verified, a consent changes, a
// decision of the moderation concerns the member or an urgent report
// reaches a moderator.
patch(Store.prototype, {
    setup() {
        super.setup(...arguments);
        /** Whether the address of the member is verified (LU-F-110 RM3). */
        this.linkup_email_verified = true;
        /** The required consents the member has not given (LU-F-111). */
        this.linkup_consent_missing = [];
        /** The resources of "Need help now"; empty, the defaults show. */
        this.linkup_help_resources = [];
        /** When the moderation reads the reports, as an administrator wrote it. */
        this.linkup_moderation_hours = "";
        /** Hours within which an urgent report is handled (LU-NF-042). */
        this.linkup_urgent_hours = 24;
        /** Decisions of the moderation the member has not read. */
        this.linkup_notice_unseen = 0;
        /** Whether the member moderates; the server checks it again. */
        this.linkup_is_moderator = false;
        /** Urgent reports in the queue of the moderator. */
        this.linkup_moderation_urgent = 0;
    },
});
