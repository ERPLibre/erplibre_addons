#!/usr/bin/env node
// Copyright 2026 TechnoLibre - Mathieu Benoit
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
//
// Compiles every Owl template under static/src/ with Odoo's own shipped
// Owl build, under node, without a browser. A template compiles to
// JAVASCRIPT SOURCE TEXT that is then handed to `new Function(...)`
// (owl.js's own `compile()`); that step needs no live DOM to fail or
// succeed, only a DOM API surface Owl's compiler calls while walking the
// parsed XML and building its static block skeletons. jsdom supplies
// that surface here, since plain node has none of it; it stays
// installed on `globalThis` for this whole script's run, not just while
// owl.js first loads, because `compile()` itself calls `new DOMParser()`
// again on every template, at call time, not load time.
//
// This is exactly the check that would have caught `t-if="not …"`
// (1f81902): `not` is not a JavaScript operator, Owl only translates
// `and`/`or`, and the resulting `new Function` call throws a
// SyntaxError naming neither the file nor the template — this script
// adds both.
//
// What it does NOT catch, stated plainly rather than left to be
// discovered by trusting it too far: a `t-call` to a template that does
// not exist. That name is resolved by `app.getTemplate(...)` inside the
// RENDER function `_compileTemplate` returns, not while compiling it —
// so it compiles cleanly here and fails only in a real browser, when
// something actually tries to render it.
//
// Requires jsdom, which is NOT one of this module's own dependencies
// (Odoo ships Owl for a real browser, never a node DOM shim): resolved
// through node's ordinary module search, so `npm install jsdom` in any
// ancestor directory of this file, or `NODE_PATH`/`JSDOM_MODULE`
// pointing at one elsewhere, makes it available.
//
// Usage: node check_templates_compile.mjs

import {readFileSync, readdirSync, statSync} from "node:fs";
import Module from "node:module";
import path from "node:path";
import {fileURLToPath} from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const staticSrcDir = path.join(here, "..", "src");
// <repo>/odoo18.0/odoo/addons/web/static/lib/owl/owl.js: five levels up
// from this file (…/static/tests) reaches <repo>/odoo18.0 itself.
const owlPath = path.join(
    here,
    "..",
    "..",
    "..",
    "..",
    "..",
    "odoo",
    "addons",
    "web",
    "static",
    "lib",
    "owl",
    "owl.js"
);

function requireJsdom() {
    const require = Module.createRequire(import.meta.url);
    try {
        return require(process.env.JSDOM_MODULE || "jsdom");
    } catch (error) {
        throw new Error(
            "jsdom is not resolvable (tried" +
                (process.env.JSDOM_MODULE ? ` "${process.env.JSDOM_MODULE}" and` : "") +
                " the default node_modules search): install it in some scratch directory and either" +
                " add it to NODE_PATH or set JSDOM_MODULE to its main file before running this script." +
                `\n(${error.message})`
        );
    }
}

const {JSDOM} = requireJsdom();
// pretendToBeVisual: true is what makes jsdom provide
// requestAnimationFrame — owl.js reads it off `window` at module LOAD
// time (`Scheduler.requestAnimationFrame = window.requestAnimationFrame...`),
// not lazily, so it has to exist before owl.js is evaluated at all.
const dom = new JSDOM("<!doctype html><html><body></body></html>", {pretendToBeVisual: true});
// Every browser global jsdom's window carries, copied onto node's own
// global object: owl.js is a browser script with no import list to read
// off, so there is no fixed set of names to name in advance (DOMTokenList,
// HTMLElement, CustomEvent, … are all used somewhere in its 6000+ lines
// besides the handful this script happens to exercise directly). A few
// properties throw merely by being read (jsdom stubs for browser APIs it
// does not implement under some sandboxes); skipped rather than allowed
// to abort the whole setup — owl.js will fail loudly and specifically if
// it actually needed one of those.
for (const name of Object.getOwnPropertyNames(dom.window)) {
    try {
        globalThis[name] = dom.window[name];
    } catch {
        /* unreadable in this sandbox; see comment above */
    }
}

function loadOwl() {
    const source = readFileSync(owlPath, "utf8");
    const moduleExports = {};
    // owl.js is a plain UMD-style script, `(function (exports) {...})
    // (this.owl = this.owl || {})`: running it as a Function bound to
    // `moduleExports` reproduces exactly what loading it as a classic
    // <script> tag does in a browser, `this` included.
    new Function(source).call(moduleExports); // eslint-disable-line no-new-func
    if (!moduleExports.owl) {
        throw new Error("owl.js ran without error but left no `this.owl` on it — unexpected build shape.");
    }
    return moduleExports.owl;
}

function findXmlFiles(dir) {
    const found = [];
    for (const entry of readdirSync(dir)) {
        const full = path.join(dir, entry);
        if (statSync(full).isDirectory()) {
            found.push(...findXmlFiles(full));
        } else if (entry.endsWith(".xml")) {
            found.push(full);
        }
    }
    return found;
}

// A template's own t-if/t-elif/t-esc/… expressions are the only place
// `not` (this bug) or a similarly untranslated Python-ism could hide;
// named so a failure reads "which file, which template" instead of
// just a generated-code dump.
function templateElementsIn(xmlSource) {
    const doc = new DOMParser().parseFromString(xmlSource, "text/xml");
    if (doc.getElementsByTagName("parsererror").length) {
        throw new Error(doc.getElementsByTagName("parsererror")[0].textContent);
    }
    return [...doc.querySelectorAll("[t-name]")].map((element) => ({
        name: element.getAttribute("t-name"),
        element,
    }));
}

const owl = loadOwl();
const app = new owl.App(null, {dev: true});
const files = findXmlFiles(staticSrcDir);

if (!files.length) {
    console.log(`No .xml files found under ${staticSrcDir}.`);
    process.exit(0);
}

let compiled = 0;
let failed = 0;
for (const file of files) {
    const relative = path.relative(staticSrcDir, file);
    const source = readFileSync(file, "utf8");
    // Parsing the file is part of this file's own report, not a
    // precondition assumed to always succeed: a malformed XML file used
    // to throw here UNCAUGHT, outside every per-file try/catch below,
    // aborting the whole scan with a raw stack trace that named neither
    // the file nor the reason — the worst possible result from the one
    // guard meant to give better information than the browser would.
    let templates;
    try {
        templates = templateElementsIn(source);
    } catch (error) {
        failed += 1;
        console.log(`  FAIL ${relative} :: ${error.message.split("\n")[0]}`);
        continue;
    }
    for (const {name, element} of templates) {
        try {
            app._compileTemplate(name, element);
            compiled += 1;
            console.log(`  ok   ${relative} :: ${name}`);
        } catch (error) {
            failed += 1;
            console.log(`  FAIL ${relative} :: ${name}`);
            console.log(`       ${error.message.split("\n")[0]}`);
        }
    }
}

console.log("");
console.log(`${compiled} compiled, ${failed} failed, ${compiled + failed} total.`);
if (failed) {
    process.exitCode = 1;
}
