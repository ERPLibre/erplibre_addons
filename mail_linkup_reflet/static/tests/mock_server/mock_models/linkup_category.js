import { getKwArgs, models } from "@web/../tests/web_test_helpers";

const CATEGORIES = [
  ["observation", "Observation", "You told me about what you observed", 10, 1],
  ["emotions", "Emotions", "You told me about your emotions", 20, 2],
  ["needs", "Needs", "You told me about your needs", 30, 3],
  ["action", "Action request", "You told me about a request", 40, false],
  [
    "inhibition",
    "Inhibition",
    "You told me about what you no longer want",
    50,
    false,
  ],
  [
    "go_listen",
    "Go listen",
    "You told me you need to be listened to",
    60,
    false,
  ],
  [
    "go_speak",
    "Go speak",
    "You told me about what you wanted to tell me",
    70,
    5,
  ],
  ["goals", "Goals", "You told me about your goal", 80, 6],
  [
    "vulnerability",
    "Vulnerability",
    "You told me about your vulnerability",
    90,
    7,
  ],
  [
    "reflection",
    "Reflection",
    "You told me you want to be better understood",
    100,
    false,
  ],
  [
    "focus",
    "Focused attention",
    "You told me about what holds your attention",
    110,
    false,
  ],
  ["team", "Team", "You told me about the team", 120, 4],
];

/** Starters of a few categories: first person, then reformulation. */
const STARTERS = {
  emotions: ["I feel:", "You feel:"],
  needs: ["I need:", "You need:"],
  action: ["I would like you to:", "Your action request is that:"],
  goals: ["My goal is:", "Your goal is:"],
};

/** The twelve categories of `data/linkup_category_data.xml`, in English. */
export class LinkupCategory extends models.ServerModel {
  _name = "linkup.category";

  _records = CATEGORIES.map(
    ([code, name, reflet_title, sequence, bar], index) => ({
      id: index + 1,
      code,
      name,
      reflet_title,
      sequence,
      in_reflet_bar: Boolean(bar),
      reflet_bar_sequence: bar || 100,
      is_cnv: index < 5,
      definition: code === "emotions" ? "What a person feels." : false,
      example_do:
        code === "emotions"
          ? "“I feel anger when I see that the rule is not respected.”"
          : false,
      example_dont: false,
      starter_self: STARTERS[code]?.[0] || false,
      starter_reflect: STARTERS[code]?.[1] || false,
      active: true,
    })
  );

  /** Simulates `linkup.category._to_store`: the code only. */
  _to_store(ids, store, fields) {
    const kwargs = getKwArgs(arguments, "ids", "store", "fields");
    store.add(
      this._name,
      this._read_format(kwargs.ids, kwargs.fields || ["code"], false)
    );
  }

  /** @param {string} code */
  _byCode(code) {
    return this._filter([["code", "=", code]])[0];
  }
}
