import { mailModels } from "@mail/../tests/mail_test_helpers";

import { defineModels, patchWithCleanup } from "@web/../tests/web_test_helpers";

import { linkupReadWatch } from "@mail_linkup_reflet/core/common/linkup_read_watch";

import { DiscussChannel } from "./mock_server/mock_models/discuss_channel";
import { LinkupBlock } from "./mock_server/mock_models/linkup_block";
import { LinkupCategory } from "./mock_server/mock_models/linkup_category";
import { LinkupHighlight } from "./mock_server/mock_models/linkup_highlight";
import { LinkupReflet } from "./mock_server/mock_models/linkup_reflet";
import { LinkupReport } from "./mock_server/mock_models/linkup_report";
import { MailMessage } from "./mock_server/mock_models/mail_message";
import { ResUsers } from "./mock_server/mock_models/res_users";
import { ResUsersSettings } from "./mock_server/mock_models/res_users_settings";

export const linkupModels = {
  ...mailModels,
  DiscussChannel,
  LinkupBlock,
  LinkupCategory,
  LinkupHighlight,
  LinkupReflet,
  LinkupReport,
  MailMessage,
  ResUsers,
  ResUsersSettings,
};

export function defineLinkupModels() {
  return defineModels(linkupModels);
}

/**
 * Stand for the visibility of the tab and of the cards, which decide when a
 * card records its reading (`linkup_read_watch.js`). Every watched card is
 * told `onScreen` at once.
 *
 * @returns {{setVisible: (visible: boolean) => void, setOnScreen: (onScreen: boolean) => void}}
 *  `setVisible` changes the visibility of the tab and fires
 *  `visibilitychange`; `setOnScreen` tells every watched card that it
 *  entered or left the screen.
 */
export function mockLinkupReading({ visible = true, onScreen = true } = {}) {
  const state = { visible, onScreen, callbacks: new Set() };
  patchWithCleanup(linkupReadWatch, {
    isPageVisible: () => state.visible,
    observe(el, onChange) {
      state.callbacks.add(onChange);
      onChange(state.onScreen);
      return () => state.callbacks.delete(onChange);
    },
  });
  return {
    setVisible(value) {
      state.visible = value;
      document.dispatchEvent(new Event("visibilitychange"));
    },
    setOnScreen(value) {
      state.onScreen = value;
      for (const callback of [...state.callbacks]) {
        callback(value);
      }
    },
  };
}
