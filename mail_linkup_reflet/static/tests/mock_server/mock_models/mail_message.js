import { mailModels } from "@mail/../tests/mail_test_helpers";
import { mailDataHelpers } from "@mail/../tests/mock_server/mail_mock_server";

import { getKwArgs } from "@web/../tests/web_test_helpers";

/** Simulates the carrier messages of `mail_linkup_reflet`. */
export class MailMessage extends mailModels.MailMessage {
  /** Links the carrier being posted, as `_message_post_after_hook` does. */
  create() {
    const result = super.create(...arguments);
    const LinkupReflet = this.env["linkup.reflet"];
    const refletId = LinkupReflet._linkupCarrierFor;
    if (refletId) {
      const [messageId] = Array.isArray(result) ? result : [result];
      LinkupReflet.write([refletId], { message_id: messageId });
    }
    return result;
  }

  _to_store(ids, store) {
    const kwargs = getKwArgs(
      arguments,
      "ids",
      "store",
      "fields",
      "for_current_user",
      "add_followers"
    );
    super._to_store(...arguments);
    if (kwargs.fields && !kwargs.fields.includes("linkup_reflet_id")) {
      return;
    }
    const LinkupReflet = this.env["linkup.reflet"];
    for (const messageId of kwargs.ids) {
      const [reflet] = LinkupReflet._filter([["message_id", "=", messageId]]);
      if (reflet) {
        store.add(this.browse(messageId), {
          linkup_reflet_id: mailDataHelpers.Store.one(
            LinkupReflet.browse(reflet.id)
          ),
        });
      }
    }
  }
}
