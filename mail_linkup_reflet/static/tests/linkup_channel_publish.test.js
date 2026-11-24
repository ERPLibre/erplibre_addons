import {
  click,
  contains,
  openDiscuss,
  start,
  startServer,
} from "@mail/../tests/mail_test_helpers";
import { after, describe, expect, test } from "@odoo/hoot";
import { onRpc } from "@web/../tests/web_test_helpers";

import { defineLinkupModels } from "./linkup_test_helpers";
import { DiscussChannel } from "./mock_server/mock_models/discuss_channel";

describe.current.tags("desktop");
defineLinkupModels();

/**
 * The settings of a channel, the form `mail.discuss_channel_view_form` as
 * `mail_linkup_reflet` extends it: the publication, read-only to whoever
 * may not change it.
 */
function useSettingsForm() {
  const previous = DiscussChannel._views;
  DiscussChannel._views = {
    form: `<form>
        <field name="name"/>
        <field name="channel_type" invisible="1"/>
        <field name="linkup_can_publish" invisible="1"/>
        <field name="linkup_published"
          invisible="channel_type != 'channel'"
          readonly="not linkup_can_publish"/>
      </form>`,
  };
  after(() => {
    DiscussChannel._views = previous;
  });
}

async function openSettings(values) {
  const pyEnv = await startServer();
  pyEnv["discuss.channel"].create({ name: "Rencontres", ...values });
  await start();
  await openDiscuss();
  await click("[title='Channel settings']", {
    parent: [".o-mail-DiscussSidebarChannel", { text: "Rencontres" }],
  });
  await contains(".o_form_view .o_field_widget[name='linkup_published']");
}

test("the creator of a channel publishes it from its settings", async () => {
  useSettingsForm();
  onRpc("discuss.channel", "web_save", ({ args }) => {
    expect.step(`web_save ${JSON.stringify(args[1])}`);
  });
  await openSettings({ linkup_can_publish: true });
  await click(".o_field_widget[name='linkup_published'] input:enabled");
  await click(".o_form_button_save");
  await expect.waitForSteps(['web_save {"linkup_published":true}']);
});

test("a member who may not publish reads the setting only", async () => {
  useSettingsForm();
  await openSettings({ linkup_can_publish: false, linkup_published: true });
  await contains(
    ".o_field_widget[name='linkup_published'] input:checked:disabled"
  );
});
