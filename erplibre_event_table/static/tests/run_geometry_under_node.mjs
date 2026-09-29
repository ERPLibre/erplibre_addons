#!/usr/bin/env node
// Copyright 2026 TechnoLibre - Mathieu Benoit
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
//
// Runs this directory's PURE test files for real, under plain node,
// without a browser. A pure test file exercises geometry.js, which is
// pure itself — no Odoo import, no DOM — so the only things standing
// between "unrunnable here" and "verified" are specifiers plain node
// cannot resolve on its own: "@odoo/hoot" (the test framework),
// "@erplibre_event_table/floor_plan/geometry" (an Odoo asset alias for a
// sibling of this file) and the fixture's relative path, which has no
// directory to resolve against once a file runs as a data: URL. All
// three are rewritten to real paths below, in each test file's SOURCE
// TEXT, purely in memory — no test file on disk is ever touched, and
// every test body runs unmodified against the actual shipped
// geometry.js.
//
// WHAT IT READS: every "*.test.js" sibling, discovered at run time,
// minus the files EXCLUDED names together with the reason each is held
// out. Discovery rather than a hand-written list, because a test file
// that is never read reports neither a pass nor a failure: the run stays
// green while not one of that file's assertions has been evaluated. The
// run prints which files it reads and which it holds out, refuses to
// finish if it reads none, and refuses to credit a file that registers
// no test.
//
// WHAT IT DOES NOT COVER: the excluded files, and any matcher beyond the
// two IMPLEMENTED_MATCHERS names — an unimplemented matcher stops the
// run before a single test executes rather than passing quietly. Odoo's
// own hoot runner, in a browser, stays the reference for everything
// this shim leaves out.
//
// Usage: node run_geometry_under_node.mjs

import assert from "node:assert/strict";
import {readFileSync, readdirSync} from "node:fs";
import path from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const geometryFile = path.join(here, "..", "src", "floor_plan", "geometry.js");
const fixtureFile = path.join(here, "visual_table_size_fixture.js");

// Test files this runner cannot execute, each with the reason it is held
// out. Naming them here — rather than leaving them out of a hand-written
// list, where an absence is indistinguishable from an oversight — is what
// lets the run REPORT what it skipped and why, so a file is never counted
// as covered by silence.
const EXCLUDED = {
    "floor_plan.test.js":
        "mounts an Owl component against a real DOM and the web client's own test helpers" +
        " (@odoo/hoot-dom, @web/../tests/web_test_helpers), which this runner does not shim",
};

const discovered = readdirSync(here)
    .filter((entry) => entry.endsWith(".test.js"))
    .sort();
const selected = discovered.filter((name) => !(name in EXCLUDED));

for (const name of discovered.filter((entry) => entry in EXCLUDED)) {
    console.log(`Skipping ${name}: ${EXCLUDED[name]}.`);
}
if (!selected.length) {
    throw new Error(
        `No runnable "*.test.js" file found in ${here} — a run with nothing to run would report a` +
            " pass it never earned."
    );
}
console.log(`Reading ${selected.length} test file(s): ${selected.join(", ")}.`);

// Refuses to report a false pass if a test file starts using a matcher
// this shim does not implement: an unrecognised ".xyz()" would otherwise
// be undefined and throw at call time in every test that reaches it,
// which would look like a wave of failures instead of naming the real
// cause. Listing the two matchers here, rather than assuming, is what
// lets this script say — not guess — that it skipped nothing.
const IMPLEMENTED_MATCHERS = ["toBe", "toEqual"];
// Plain JS Number/String/Array methods that happen to match the same
// ".to<Word>(" shape as a hoot matcher (Number.toFixed on a coordinate
// builds a dedup key, for one — nothing to do with hoot); named
// explicitly so the check above stays honest about what it excludes
// instead of silently narrowing the scan.
const KNOWN_NON_MATCHERS = [
    "toFixed",
    "toString",
    "toLowerCase",
    "toUpperCase",
    "toISOString",
    "toJSON",
    "toSorted",
    "toReversed",
];

function matchersIn(source) {
    return [...new Set([...source.matchAll(/\.(to[A-Z][A-Za-z]*)\(/g)].map((m) => m[1]))]
        .filter((name) => !KNOWN_NON_MATCHERS.includes(name))
        .sort();
}

// Every selected file is scanned BEFORE any of them runs: a shim that
// cannot honestly evaluate one file's assertions must not first print a
// screenful of passes from the others.
const sources = new Map();
for (const name of selected) {
    const source = readFileSync(path.join(here, name), "utf8");
    sources.set(name, source);
    const usedMatchers = matchersIn(source);
    const unknown = usedMatchers.filter((matcher) => !IMPLEMENTED_MATCHERS.includes(matcher));
    if (unknown.length) {
        throw new Error(
            `${name} calls ${unknown.map((m) => `.${m}()`).join(", ")}, which this runner does not` +
                " implement yet — extend it before trusting its result."
        );
    }
    console.log(`  ${name} uses ${usedMatchers.join(", ")} (all implemented below).`);
}

// --- Minimal @odoo/hoot shim: describe/test run synchronously, in
// registration order, exactly as hoot itself runs these files' flat
// (non-nested) describe blocks. ---
let currentFile = "";
let suite = "";
let passed = 0;
let failed = 0;
let testsInFile = 0;
const failures = [];

function describe(name, fn) {
    suite = name;
    fn();
}

function test(name, fn) {
    const label = `${currentFile} > ${suite} > ${name}`;
    testsInFile += 1;
    try {
        fn();
        passed += 1;
        console.log(`  ok   ${label}`);
    } catch (error) {
        failed += 1;
        failures.push({label, error});
        console.log(`  FAIL ${label}`);
        console.log(`       ${error.message}`);
    }
}

function expect(actual) {
    return {
        toBe(expected) {
            assert.strictEqual(actual, expected);
        },
        toEqual(expected) {
            assert.deepStrictEqual(actual, expected);
        },
    };
}

// The shim module reaches back into this scope through a global rather
// than closing over describe/test/expect directly, since it is handed
// to `import()` as a separate, independently-evaluated data: URL module.
globalThis.__nodeTestRunner = {describe, test, expect};
const shimSource = [
    "export function describe(name, fn) { globalThis.__nodeTestRunner.describe(name, fn); }",
    "export function test(name, fn) { globalThis.__nodeTestRunner.test(name, fn); }",
    "export function expect(actual) { return globalThis.__nodeTestRunner.expect(actual); }",
].join("\n");

function dataUrlFor(code) {
    return `data:text/javascript;base64,${Buffer.from(code, "utf8").toString("base64")}`;
}

// replaceAll, not replace: a string pattern handed to
// String.prototype.replace rewrites only the FIRST occurrence, so a
// second `from "@odoo/hoot"` in the same file would reach node as a bare
// specifier it cannot resolve, and the import error would take down that
// whole file's tests over a rewrite that simply stopped too early.
function rewriteSpecifiers(source) {
    return source
        .replaceAll('from "@odoo/hoot"', `from ${JSON.stringify(dataUrlFor(shimSource))}`)
        .replaceAll(
            'from "@erplibre_event_table/floor_plan/geometry"',
            `from ${JSON.stringify(pathToFileURL(geometryFile).href)}`
        )
        // A test file also imports its fixture by a RELATIVE specifier,
        // resolved by a real browser against the test file's own URL —
        // this module instead runs the source as a data: URL (below),
        // which has no directory of its own for a relative specifier to
        // resolve against, so it needs the same rewrite the two
        // absolute-looking specifiers above already get.
        .replaceAll('from "./visual_table_size_fixture.js"', `from ${JSON.stringify(pathToFileURL(fixtureFile).href)}`);
}

for (const name of selected) {
    currentFile = name;
    suite = "";
    testsInFile = 0;
    console.log("");
    console.log(`--- ${name}`);
    try {
        await import(dataUrlFor(rewriteSpecifiers(sources.get(name))));
    } catch (error) {
        // A file that fails to load registers no test at all: counted as
        // a failure of its own, and the remaining files still run, so the
        // report names what broke instead of stopping at the first one.
        failed += 1;
        failures.push({label: `${name} > (module)`, error});
        console.log(`  FAIL ${name} > (module) did not load`);
        console.log(`       ${error.message}`);
        continue;
    }
    if (!testsInFile) {
        // A "*.test.js" that registers nothing would otherwise add zero
        // to both counters and leave the run green — the same false
        // verification as a file never read at all.
        failed += 1;
        failures.push({label: `${name} > (module)`, error: new Error("registers no test")});
        console.log(`  FAIL ${name} > (module) registers no test`);
    }
}

console.log("");
console.log(`${passed} passed, ${failed} failed, ${passed + failed} total, over ${selected.length} file(s).`);
if (failed) {
    process.exitCode = 1;
}
