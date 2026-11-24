import {_t} from "@web/core/l10n/translation";

/**
 * The label of each consent, by purpose (`linkup.consent.purpose`), as the
 * signup form words them.
 */
export function linkupConsentLabels() {
    return {
        terms: _t("I accept the terms of use."),
        privacy: _t("I accept the privacy policy."),
        sensitive_data: _t("I agree that LinkUp processes the sensitive information my reflections may hold."),
        link_visibility: _t("My links are visible to my links."),
        energy_visibility: _t("My energy is visible to my links."),
        notifications: _t("LinkUp notifies me of my reflections and invitations."),
        ai: _t("LinkUp may suggest themes and wordings with artificial intelligence."),
    };
}

/** What the consent to sensitive information covers (LU-NF-050). */
export function linkupSensitiveHelp() {
    return _t(
        "A reflection may tell emotions, needs, health or private life. Without this consent, you send no reflection."
    );
}
