import {LinkupRefletView} from "@mail_linkup_reflet/views/reflet_view/reflet_view";

import {LinkupCommunityNotice} from "./linkup_community_notice";
import {LinkupModerationBanner} from "./linkup_moderation_banner";

// The banners of the consents, of the verification and of the moderation,
// under the header of the Reflet view (reflet_view_patch.xml).
LinkupRefletView.components = {...LinkupRefletView.components, LinkupCommunityNotice, LinkupModerationBanner};
