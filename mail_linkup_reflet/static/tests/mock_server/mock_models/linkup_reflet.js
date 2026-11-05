import { mailDataHelpers } from "@mail/../tests/mock_server/mail_mock_server";

import {
  fields,
  getKwArgs,
  makeKwArgs,
  models,
  serverState,
} from "@web/../tests/web_test_helpers";

/**
 * Simulates `linkup.reflet`: the card of `_to_store`, the draft, the
 * sending with its carrier message, the answers and the follow-up options,
 * and `linkup_channel_info`.
 *
 * The server computes `holds_turn` from the turn of the link; here it is a
 * field the tests set, which the actions move. The hidden themes of a
 * precision are `hidden_category_ids`, given to the current user only when
 * they wrote the precision or once the guess is made, as the private part
 * of the server is.
 */
export class LinkupReflet extends models.ServerModel {
  _name = "linkup.reflet";

  holds_turn = fields.Boolean();
  hidden_category_ids = fields.Many2many({ relation: "linkup.category" });

  /** Id of the reflection whose carrier message is being posted. */
  _linkupCarrierFor = null;

  _to_store(ids, store) {
    const kwargs = getKwArgs(arguments, "ids", "store");
    /** @type {import("mock_models").ResUsers} */
    const ResUsers = this.env["res.users"];
    for (const reflet of this.browse(kwargs.ids)) {
      const [author] = ResUsers.browse(reflet.author_id);
      const [recipient] = ResUsers.browse(reflet.recipient_id);
      const withdrawn = reflet.state === "withdrawn";
      const categoryId = !withdrawn && reflet.category_id;
      if (categoryId) {
        this.env["linkup.category"]._to_store([categoryId], store);
      }
      const hiddenIds = reflet.hidden_category_ids || [];
      const revealed =
        hiddenIds.length &&
        (reflet.author_id === serverState.userId ||
          ["found", "missed"].includes(reflet.guess_state));
      if (revealed) {
        this.env["linkup.category"]._to_store(hiddenIds, store);
        store.add(this._name, {
          id: reflet.id,
          revealed_category_ids: hiddenIds.map((id) => ({ id })),
          primary_category_id: { id: hiddenIds[0] },
        });
      }
      if (reflet.guessed_category_id) {
        this.env["linkup.category"]._to_store(
          [reflet.guessed_category_id],
          store
        );
      }
      if (
        reflet.recipient_ignored &&
        reflet.recipient_id === serverState.userId
      ) {
        store.add(this._name, { id: reflet.id, recipient_ignored: true });
      }
      store.add(this._name, {
        id: reflet.id,
        kind: reflet.kind || "initial",
        state: reflet.state,
        response_state: reflet.response_state || "none",
        guess_state: reflet.guess_state || "none",
        holds_turn: Boolean(reflet.holds_turn),
        message_id: reflet.message_id || false,
        author: author ? { id: author.partner_id, type: "partner" } : false,
        recipient: recipient
          ? { id: recipient.partner_id, type: "partner" }
          : false,
        category_id: categoryId ? { id: categoryId } : false,
        guessed_category_id: reflet.guessed_category_id
          ? { id: reflet.guessed_category_id }
          : false,
        parent_id: reflet.parent_id || false,
        read_date: reflet.read_date || false,
        you_said: !withdrawn && reflet.you_said,
        understood: !withdrawn && reflet.understood,
        body_text: !withdrawn && reflet.body_text,
      });
    }
  }

  /** @param {number} channelId */
  _linkupPartnerIds(channelId) {
    return this.env["discuss.channel.member"]
      ._filter([["channel_id", "=", channelId]])
      .map((member) => member.partner_id)
      .filter(Boolean);
  }

  action_save_draft(vals) {
    const kwargs = getKwArgs(arguments, "vals");
    const values = { ...kwargs.vals };
    const [draft] = this._filter([
      ["author_id", "=", serverState.userId],
      ["state", "=", "draft"],
    ]);
    if (draft) {
      this.write([draft.id], values);
      return draft.id;
    }
    return this.create({
      ...values,
      author_id: serverState.userId,
      state: "draft",
    });
  }

  action_discard_draft(ids) {
    this.unlink(ids);
    return true;
  }

  action_send(ids, recipient_id) {
    const kwargs = getKwArgs(arguments, "ids", "recipient_id");
    const [reflet] = this.browse(kwargs.ids);
    const [recipient] = this.env["res.users"].browse(kwargs.recipient_id);
    const [channel] = this.env["discuss.channel"]
      ._filter([["channel_type", "=", "chat"]])
      .filter((chat) =>
        this._linkupPartnerIds(chat.id).includes(recipient.partner_id)
      );
    this.write([reflet.id], {
      state: "sent",
      recipient_id: recipient.id,
      channel_id: channel.id,
    });
    this._linkupPostCarrier(reflet.id, channel.id, "sent you a reflection.");
    return true;
  }

  /**
   * Post the carrier message of a reflection as the current user, linked
   * to it as `_message_post_after_hook` does.
   */
  _linkupPostCarrier(refletId, channelId, sentence) {
    const [author] = this.env["res.partner"].browse(serverState.partnerId);
    this._linkupCarrierFor = refletId;
    this.env["discuss.channel"].message_post(
      channelId,
      makeKwArgs({
        body: `<p>${author.name} ${sentence}</p>`,
        message_type: "comment",
        subtype_xmlid: "mail.mt_comment",
      })
    );
    this._linkupCarrierFor = null;
  }

  /** Give the turn of the pair to `refletId`. */
  _linkupMoveTurn(refletId) {
    const [reflet] = this.browse(refletId);
    const others = this._filter([
      ["channel_id", "=", reflet.channel_id],
      ["holds_turn", "=", true],
    ]).map((record) => record.id);
    this.write(others, { holds_turn: false });
    this.write([refletId], { holds_turn: true });
  }

  /** Create the next reflection of the chain, by the current user. */
  _linkupChild(parentId, kind, values) {
    const [parent] = this.browse(parentId);
    const childId = this.create({
      kind,
      state: "sent",
      author_id: serverState.userId,
      recipient_id: parent.author_id,
      channel_id: parent.channel_id,
      parent_id: parent.id,
      ...values,
    });
    this._linkupMoveTurn(childId);
    this._linkupPostCarrier(childId, parent.channel_id, `answered (${kind}).`);
    return childId;
  }

  action_mark_read(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    const [reflet] = this.browse(kwargs.ids);
    if (!reflet.read_date) {
      this.write(kwargs.ids, { read_date: "2026-01-01 10:00:00" });
    }
    return true;
  }

  /** Confirms, and opens the conversation as `linkup.link._linkup_activate`. */
  action_confirm(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { state: "confirmed" });
    this._linkupMoveTurn(kwargs.ids[0]);
    const [reflet] = this.browse(kwargs.ids);
    const DiscussChannel = this.env["discuss.channel"];
    const [channel] = DiscussChannel.browse(reflet.channel_id);
    if (channel && !channel.linkup_start_rule_satisfied) {
      DiscussChannel.write([channel.id], { linkup_start_rule_satisfied: true });
      this.env["bus.bus"]._sendone(
        channel,
        "mail.record/insert",
        new mailDataHelpers.Store(DiscussChannel.browse(channel.id), {
          linkup_start_rule: channel.linkup_start_rule,
          linkup_start_rule_satisfied: true,
        }).get_result()
      );
    }
    return true;
  }

  /** Withdraws an unread sent reflection, as the server does. */
  action_withdraw(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { state: "withdrawn" });
    return true;
  }

  action_reject(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { state: "rejected" });
    return true;
  }

  action_ignore(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { recipient_ignored: true });
    return true;
  }

  action_mark_inaccurate(ids, body) {
    const kwargs = getKwArgs(arguments, "ids", "body");
    this.write(kwargs.ids, {
      state: "inaccurate",
      body_text: kwargs.body || false,
    });
    return true;
  }

  action_answer_exact(ids, body) {
    const kwargs = getKwArgs(arguments, "ids", "body");
    this.write(kwargs.ids, { response_state: "exact" });
    return this._linkupChild(kwargs.ids[0], "answer_exact", {
      body_text: kwargs.body || false,
    });
  }

  action_answer_precision(ids, body, hidden_category_ids) {
    const kwargs = getKwArgs(arguments, "ids", "body", "hidden_category_ids");
    const hidden = kwargs.hidden_category_ids || [];
    this.write(kwargs.ids, { response_state: "precision" });
    return this._linkupChild(kwargs.ids[0], "precision", {
      body_text: kwargs.body,
      guess_state: hidden.length ? "pending" : "none",
      hidden_category_ids: hidden,
    });
  }

  action_guess(ids, category_id) {
    const kwargs = getKwArgs(arguments, "ids", "category_id");
    const [reflet] = this.browse(kwargs.ids);
    const guess_state = reflet.hidden_category_ids.includes(kwargs.category_id)
      ? "found"
      : "missed";
    this.write(kwargs.ids, {
      guess_state,
      guessed_category_id: kwargs.category_id,
    });
    return guess_state;
  }

  action_continue(ids, category_id, body) {
    const kwargs = getKwArgs(arguments, "ids", "category_id", "body");
    const [reflet] = this.browse(kwargs.ids);
    if (reflet.kind === "self_disclosure") {
      this.write(kwargs.ids, { response_state: "precision" });
    }
    return this._linkupChild(kwargs.ids[0], "continue", {
      category_id: kwargs.category_id,
      understood: kwargs.body,
    });
  }

  action_self_disclosure(ids, category_id, body) {
    const kwargs = getKwArgs(arguments, "ids", "category_id", "body");
    return this._linkupChild(kwargs.ids[0], "self_disclosure", {
      category_id: kwargs.category_id || false,
      body_text: kwargs.body,
    });
  }

  action_close(ids, body) {
    const kwargs = getKwArgs(arguments, "ids", "body");
    return this._linkupChild(kwargs.ids[0], "close", {
      body_text: kwargs.body || false,
    });
  }

  /**
   * The LinkUp members other than the current user, those holding an unread
   * reflection sent to the current user first, then by name. The server
   * keeps the members of the scope and orders by the last interaction of
   * the pair; the tests give the contacts in the order they expect. The
   * link is `active` for the users marked `linkup_active_link`, and the
   * conversation of a contact is the direct conversation the current user
   * shares with them, if any.
   */
  linkup_reflet_view_info() {
    const unread = (user) =>
      this._filter([
        ["author_id", "=", user.id],
        ["recipient_id", "=", serverState.userId],
        ["state", "=", "sent"],
      ]).filter((reflet) => !reflet.read_date).length;
    const contacts = this.env["res.users"]
      ._filter([
        ["linkup_is_member", "=", true],
        ["id", "!=", serverState.userId],
      ])
      .filter((user) => !user.share && user.active !== false)
      .map((user) => {
        const [partner] = this.env["res.partner"].browse(user.partner_id);
        return {
          user_id: user.id,
          partner_id: user.partner_id,
          name: partner?.name || user.name,
          unread_count: unread(user),
          link_state: user.linkup_active_link ? "active" : "none",
          last_interaction_date: false,
          needs_real_world: !user.linkup_active_link,
          channel_id: this._linkupChatWith(user.partner_id),
        };
      })
      .sort(
        (a, b) =>
          Boolean(b.unread_count) - Boolean(a.unread_count) ||
          a.name.localeCompare(b.name)
      );
    const [draft] = this._filter([
      ["author_id", "=", serverState.userId],
      ["state", "=", "draft"],
    ]);
    const sent = this._filter([
      ["author_id", "=", serverState.userId],
      ["state", "=", "sent"],
    ])
      .filter((reflet) => (reflet.kind || "initial") === "initial")
      .map((reflet) => reflet.id)
      .sort((a, b) => b - a);
    const store = new mailDataHelpers.Store();
    this._to_store(sent, store);
    for (const reflet of this.browse(sent)) {
      const [recipient] = this.env["res.users"].browse(reflet.recipient_id);
      const [partner] = this.env["res.partner"].browse(recipient?.partner_id);
      if (partner) {
        store.add("res.partner", { id: partner.id, name: partner.name });
      }
    }
    return {
      contacts,
      draft: draft ? this._linkupDraftInfo(draft) : false,
      sent_ids: sent,
      store: store.get_result(),
    };
  }

  /**
   * The history of the pair of a chat, filtered by visible category and by
   * state, the most recent first, as `linkup_history`.
   */
  linkup_history(channel_id, category_id, state) {
    const kwargs = getKwArgs(arguments, "channel_id", "category_id", "state");
    const reflets = this._filter([
      ["channel_id", "=", kwargs.channel_id],
      ["state", "!=", "draft"],
    ])
      .filter(
        (reflet) =>
          (!kwargs.category_id || reflet.category_id === kwargs.category_id) &&
          (!kwargs.state || reflet.state === kwargs.state)
      )
      .sort((a, b) => b.id - a.id)
      .map((reflet) => reflet.id);
    const store = new mailDataHelpers.Store();
    this._to_store(reflets, store);
    return {
      available: true,
      reflet_ids: reflets,
      count: reflets.length,
      store: store.get_result(),
    };
  }

  /** The direct conversation of the current user with a partner, or false. */
  _linkupChatWith(partnerId) {
    const chat = this.env["discuss.channel"]
      ._filter([["channel_type", "=", "chat"]])
      .find((channel) => {
        const partnerIds = this._linkupPartnerIds(channel.id);
        return (
          partnerIds.length === 2 &&
          partnerIds.includes(serverState.partnerId) &&
          partnerIds.includes(partnerId)
        );
      });
    return chat ? chat.id : false;
  }

  _linkupDraftInfo(draft) {
    return {
      id: draft.id,
      category_id: draft.category_id || false,
      you_said: draft.you_said || "",
      understood: draft.understood || "",
      real_world_declared: Boolean(draft.real_world_declared),
      real_world_date: draft.real_world_date || false,
    };
  }

  linkup_channel_info(channel_id) {
    const kwargs = getKwArgs(arguments, "channel_id");
    const [channel] = this.env["discuss.channel"].browse(kwargs.channel_id);
    if (!channel || channel.channel_type !== "chat") {
      return { available: false };
    }
    const partnerIds = this._linkupPartnerIds(channel.id).filter(
      (partnerId) => partnerId !== serverState.partnerId
    );
    const [recipient] = this.env["res.users"]._filter([
      ["partner_id", "in", partnerIds],
      ["linkup_is_member", "=", true],
    ]);
    if (!recipient) {
      return { available: false };
    }
    const reflets = this._filter([
      ["channel_id", "=", channel.id],
      ["state", "!=", "draft"],
    ]).sort((a, b) => b.id - a.id);
    const states = reflets
      .filter((r) => r.kind === "initial")
      .map((r) => r.state);
    let link_state = "none";
    if (states.includes("confirmed")) {
      link_state = "active";
    } else if (states.includes("sent")) {
      link_state = "pending";
    } else if (states.length) {
      link_state = "closed";
    }
    const recent = reflets.slice(0, 5).map((reflet) => reflet.id);
    const store = new mailDataHelpers.Store();
    this._to_store(recent, store);
    const [draft] = this._filter([
      ["author_id", "=", serverState.userId],
      ["state", "=", "draft"],
    ]);
    return {
      available: true,
      can_send: true,
      recipient_id: recipient.id,
      link_state,
      first_link_date: false,
      needs_real_world: link_state !== "active",
      reflet_count: reflets.length,
      reflet_ids: recent,
      draft: draft ? this._linkupDraftInfo(draft) : false,
      blocked_by_me: this.env["linkup.block"]
        ._filter([["blocker_id", "=", serverState.userId]])
        .some((block) => block.blocked_id === recipient.id),
      store: store.get_result(),
    };
  }
}
