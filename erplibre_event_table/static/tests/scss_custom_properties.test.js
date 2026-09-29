/** @odoo-module **/
// Copyright 2026 TechnoLibre - Mathieu Benoit
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
//
// Pins ONE rule for the whole module: no stylesheet of this module reaches
// for a Bootstrap custom property. The rule, not the symptom — a colour put
// back by hand is undone by the next hand, while this fails the build.
//
// WHY THE RULE. The Odoo backend compiles Bootstrap's variables into values
// and publishes no `:root` block, so a `--bs-` property is defined nowhere,
// at no level of the DOM, from a leaf element up to `html`. A custom
// property that does not resolve makes its WHOLE declaration invalid at
// computed-value time: the declaration is dropped, a fill computes to
// `rgba(0, 0, 0, 0)` and a border shorthand to `0px none`, while every
// declaration around it that names no custom property still applies. The
// stylesheet is loaded, the rules match, the classes land — and the colours
// are simply absent. Nothing in the browser reports it. Write the colour as
// a SCSS variable of the bundle ($primary, $body-bg, $border-color, …): it
// compiles to a value, and each colour scheme recompiles the file with its
// own palette, so one declaration serves light and dark alike.
//
// WHERE IT RUNS. Both runners, each checking the end of the chain it can
// reach: under plain node (run_geometry_under_node.mjs, the fast make
// target) it reads the SCSS SOURCES, which is where the mistake is written;
// in a browser (the hoot suite) it reads the COMPILED RULES, which is where
// the mistake survives. Neither import is shared, so the file branches once,
// at registration, on the only thing that tells the two apart.
import {describe, expect, test} from "@odoo/hoot";

// The forbidden opening, split so this file's own explanations can name it
// without the check having to tell code from comment.
const NEEDLE = `var(${"--bs-"}`;
// The short form, for the runner that prints only the compared value and
// truncates it: it says what is wrong and where the long form is.
const BRIEF =
    "A `--bs-` custom property resolves to nothing in the Odoo backend, so its whole" +
    " declaration is dropped and the element paints nothing — see the head of" +
    " static/tests/scss_custom_properties.test.js. Offending rules:";
const WHY =
    "A `--bs-` custom property is defined nowhere in the Odoo backend, so the whole" +
    " declaration holding it is invalid at computed-value time and is dropped: the" +
    " element keeps its geometry and paints no colour at all, silently. Take the colour" +
    " from a SCSS variable of the bundle instead ($primary, $body-bg, $border-color," +
    " $body-color, $warning, $link-color, $o-view-background-color, …), which compiles" +
    " to a value and is recompiled per colour scheme.";

const UNDER_NODE = typeof document === "undefined";

// Reads the module's own SCSS sources. Resolves them from the RUNNING
// script rather than from the working directory, which differs between a
// run from the repository root and a run from this directory.
function readScssSources() {
    const getBuiltin = typeof process === "undefined" ? null : process.getBuiltinModule;
    if (typeof getBuiltin !== "function") {
        throw new Error(
            "process.getBuiltinModule is missing (node 22.3 or later), so the SCSS sources" +
                " cannot be read — a guard that reads nothing reports a pass it never earned."
        );
    }
    const fs = getBuiltin("node:fs");
    const path = getBuiltin("node:path");
    const srcDir = path.join(path.dirname(process.argv[1]), "..", "src");
    if (!fs.existsSync(srcDir)) {
        throw new Error(
            `No "static/src" directory at ${srcDir}: this guard resolves the module from the` +
                " script node was started with, and that script is not in static/tests."
        );
    }
    const files = [];
    const walk = (dir) => {
        for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                walk(full);
            } else if (entry.name.endsWith(".scss")) {
                files.push([path.relative(srcDir, full), fs.readFileSync(full, "utf8")]);
            }
        }
    };
    walk(srcDir);
    return files;
}

// Every rule of this module the browser actually holds, as [where, text].
// Selectors are how a rule is attributed here: the module's classes all
// carry the same prefix, and no other bundle writes it.
function readCompiledRules() {
    const rules = [];
    for (const sheet of document.styleSheets) {
        let list;
        try {
            list = sheet.cssRules;
        } catch {
            // A stylesheet served from another origin refuses its rules.
            continue;
        }
        for (const rule of list) {
            if (rule.selectorText && rule.selectorText.includes("o_event_table")) {
                rules.push([rule.selectorText, rule.cssText]);
            }
        }
    }
    return rules;
}

describe("the module's stylesheets name no Bootstrap custom property", () => {
    if (UNDER_NODE) {
        test("no SCSS source of the module reaches for one", () => {
            const files = readScssSources();
            if (!files.length) {
                throw new Error(
                    "Not one .scss file found under static/src — a guard with nothing to read" +
                        " reports a pass it never earned."
                );
            }
            const offences = [];
            for (const [name, source] of files) {
                source.split("\n").forEach((line, index) => {
                    if (line.includes(NEEDLE)) {
                        offences.push(`  ${name}:${index + 1}  ${line.trim()}`);
                    }
                });
            }
            if (offences.length) {
                throw new Error(
                    `${offences.length} declaration(s) reach for a Bootstrap custom` +
                        ` property:\n${offences.join("\n")}\n\n${WHY}`
                );
            }
            expect(offences.length).toBe(0);
        });
    } else {
        // The reason rides inside the COMPARED VALUE rather than being
        // thrown or handed to the matcher as a message. The browser runner
        // reports an error raised in a test body as "unverified error(s)"
        // and drops its text, and it reads the matcher's default wording
        // rather than a custom one — either way a guard that explains
        // itself arrives mute at the one moment it has something to say.
        // What it does print is the value that failed the comparison, so
        // the explanation is the head of that value. The node branch above
        // throws instead, because that runner prints an error's message.
        test("no compiled rule of the module carries one", () => {
            const rules = readCompiledRules();
            const offences = rules
                .filter(([, text]) => text.includes(NEEDLE))
                .map(([selector]) => selector);
            // Below ten the browser is serving something other than this
            // module's own bundle, and an empty scan would pass for a
            // clean one. The floor plan alone writes more rules than that.
            const verdict = [];
            if (rules.length < 10) {
                verdict.push(
                    `Only ${rules.length} rule(s) of this module are in the CSSOM, so the` +
                        " stylesheet is not being served and this check proves nothing."
                );
            }
            if (offences.length) {
                verdict.push(BRIEF, ...offences);
            }
            expect(verdict).toEqual([], {message: WHY});
        });
    }
});
