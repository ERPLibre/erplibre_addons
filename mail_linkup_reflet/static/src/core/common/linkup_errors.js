import {_t} from "@web/core/l10n/translation";
import {ConnectionLostError, RPCError} from "@web/core/network/rpc";

/**
 * The error catalogue of LinkUp on the client (LU-F-093): the codes of the
 * server (`exceptions.LINKUP_ERROR_CODES`, carried in
 * `error.data.context.linkup_code`) and three codes of the client itself:
 *
 * - `network`: the request did not reach the server, or got no answer;
 * - `session`: the session expired (`odoo.http.SessionExpiredException`);
 * - `media_denied`: the browser refuses the microphone or the camera.
 *
 * The client relies on the code, never on the text of the server.
 * `linkup.cap_reached` belongs to the scoring module, which adds its own
 * message; any other code gets the generic one.
 */
export const LINKUP_CLIENT_CODES = ["network", "session", "media_denied"];

/** The server codes this module explains, in the order of the catalogue. */
export const LINKUP_SERVER_CODES = [
    "linkup.unavailable",
    "linkup.already_answered",
    "linkup.expired",
    "linkup.rate_limited",
    "linkup.start_rule",
    "linkup.not_verified",
    "linkup.consent_required",
    "linkup.invite_expired",
    "linkup.invite_used",
    "linkup.invite_cancelled",
    "linkup.validation",
];

/** The message of a code of the catalogue. */
export function linkupCodeMessage(code) {
    switch (code) {
        case "network":
            return _t("Connection lost, try again.");
        case "session":
            return _t("Your session expired: log in again.");
        case "media_denied":
            return _t("Allow the microphone or the camera to call.");
        case "linkup.already_answered":
            return _t("This reflection has already been answered.");
        case "linkup.expired":
            return _t("This reflection is no longer available.");
        case "linkup.unavailable":
            return _t("Sending is not possible.");
        case "linkup.rate_limited":
            return _t("Too many sendings for now, try again later.");
        case "linkup.start_rule":
            return _t("Start with a reflection of a real exchange.");
        case "linkup.not_verified":
            return _t("Confirm your email address first.");
        case "linkup.consent_required":
            return _t("Accept the conditions of LinkUp first.");
        case "linkup.validation":
            return _t("Check the reflection before sending it.");
        case "linkup.invite_expired":
            return _t("This invitation has expired.");
        case "linkup.invite_used":
            return _t("This invitation has already been used.");
        case "linkup.invite_cancelled":
            return _t("This invitation was cancelled.");
    }
    return _t("The reflection could not be processed.");
}

/** Messages of `linkup.validation` refusals, by the field they name. */
export function linkupFieldMessage(field) {
    switch (field) {
        case "category_id":
            return _t("Choose a category.");
        case "you_said":
            return _t("Fill in “You told me”.");
        case "understood":
            return _t("Fill in “I understood that”.");
        case "recipient_id":
            return _t("Choose the person who told you this.");
        case "real_world_declared":
            return _t("Confirm that this exchange took place in person.");
        case "body_text":
            return _t("Write your text.");
        case "hidden_category_ids":
            return _t("Choose fewer hidden themes.");
        case "guess_state":
            return _t("Guess the hidden theme first.");
        case "email":
            return _t("Enter a valid email address.");
        case "draft":
            return _t("Send or delete your current draft first.");
    }
    return null;
}

/**
 * An error of the client, shaped as `linkupErrorInfo` returns them.
 *
 * @param {string} code a code of `LINKUP_CLIENT_CODES`, or of the server
 * @returns {{code: string, field: undefined, message: string}}
 */
export function linkupClientError(code) {
    return {code, field: undefined, message: linkupCodeMessage(code)};
}

/**
 * The message to show for an error of a LinkUp action, or `null` when the
 * error is not one the LinkUp views explain, which is then rethrown to
 * the error dialog of the web client.
 *
 * A `linkup.validation` refusal of a text too long gives its limit; any
 * other one names the field when the client knows it, and otherwise shows
 * the translated message of the server.
 *
 * @param {Error} error
 * @returns {{code: string, field: string|undefined, message: string}|null}
 */
export function linkupErrorInfo(error) {
    if (error instanceof ConnectionLostError) {
        return linkupClientError("network");
    }
    if (!(error instanceof RPCError)) {
        return null;
    }
    if (error.data?.name === "odoo.http.SessionExpiredException") {
        return linkupClientError("session");
    }
    const context = error.data?.context || {};
    const code = context.linkup_code;
    if (!code) {
        return null;
    }
    const field = context.linkup_field;
    let message = linkupCodeMessage(code);
    if (code === "linkup.validation") {
        message = context.linkup_limit
            ? _t("This text holds at most %(count)s characters.", {count: context.linkup_limit})
            : linkupFieldMessage(field) || error.data?.message || message;
    }
    return {code, field, message};
}

/**
 * Whether the browser already refuses the microphone, or the camera for a
 * video call, as the Permissions API tells it. A browser without that API,
 * or which does not know these permissions, is not refusing: the call
 * then asks as usual.
 *
 * @param {{camera?: boolean}} [options]
 * @returns {Promise<boolean>}
 */
export async function linkupMediaDenied({camera = false} = {}) {
    const permissions = globalThis.navigator?.permissions;
    if (!permissions?.query) {
        return false;
    }
    const names = camera ? ["microphone", "camera"] : ["microphone"];
    try {
        const states = await Promise.all(names.map((name) => permissions.query({name})));
        return states.some((status) => status.state === "denied");
    } catch {
        return false;
    }
}
