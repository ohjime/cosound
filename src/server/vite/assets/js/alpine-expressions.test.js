import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// Every Alpine expression in every template has to actually compile.
//
// Alpine does not evaluate an attribute on a line of its own — it splices the
// expression into one line (alpinejs, generateFunctionFromString):
//
//     with (scope) { __self.result = <expr> }; __self.finished = true; ...
//
// So a `//` comment inside a *single-line* attribute comments out the rest of
// the expression and the closing braces Alpine appended: the attribute stops
// parsing, Alpine logs once and carries on with an undefined scope, and every
// handler on that element quietly becomes a no-op. No crash, no blank page,
// just a component that does nothing. c-studio-builder shipped that way — two
// `//` notes inside its 3.6k-character x-data took out the `+` tab, the drop
// target and the file inputs together.
//
// The same splice makes any unbalanced brace or stray token fatal in the same
// silent way, which is what this test is really for. A `//` in a genuinely
// multi-line attribute (see cotton/core_deck.html) is fine — the newline ends
// the comment — and this compiles it to prove it rather than banning it.
//
// Notes about a long expression are still safer in the HTML comment above the
// element, where no formatter can join them onto the code.

const TEMPLATE_ROOT = fileURLToPath(new URL("../../../src", import.meta.url));

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// Attributes Alpine evaluates as JavaScript. x-ref/x-cloak/x-teleport/x-id take
// plain strings and x-transition:* takes class names, so none of those are
// expressions to compile.
function isAlpineExpression(name) {
    if (name.startsWith("x-transition")) return false;
    if (["x-ref", "x-cloak", "x-teleport", "x-id", "x-modelable"].includes(name)) {
        return false;
    }
    if (name.startsWith("x-")) return true;
    // Alpine's shorthands for x-on and x-bind. `hx-on:` is htmx's, not Alpine's.
    return (name.startsWith("@") || name.startsWith(":")) && !name.startsWith(":hx-on");
}

function htmlFiles(dir) {
    const found = [];
    for (const entry of readdirSync(dir)) {
        if (entry === "__pycache__" || entry === "node_modules") continue;
        const path = join(dir, entry);
        if (statSync(path).isDirectory()) found.push(...htmlFiles(path));
        else if (entry.endsWith(".html")) found.push(path);
    }
    return found;
}

const IF_BLOCK = /\{%\s*if\b[^%]*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}/s;

/**
 * The two shapes a template can render an attribute into: every `{% if %}`
 * taken, and every one skipped. Both have to compile, because both ship.
 */
function renderings(value) {
    return [true, false].map((taken) => {
        let out = value;
        while (IF_BLOCK.test(out)) {
            out = out.replace(IF_BLOCK, (_, whenTrue, whenFalse = "") => (
                taken ? whenTrue : whenFalse
            ));
        }
        // Whatever tags are left stand in as a bare identifier, so both
        // `$store.{{ name }}.layers` and `id === {{ sound.id }}` stay
        // parseable. What a tag renders is not this test's business.
        return out
            .replace(/\{\{.*?\}\}/gs, "dj")
            .replace(/\{%.*?%\}/gs, "dj")
            .replace(/&amp;/g, "&")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .replace(/&#39;|&#x27;/g, "'")
            .replace(/&quot;/g, '"');
    });
}

// x-for is `item in items` / `(item, i) in items`, which is not an expression
// on its own — only its right-hand side is.
function compilable(name, value) {
    if (name !== "x-for") return value;
    const match = value.match(/\s+in\s+(.*)$/s);
    return match ? match[1] : value;
}

function compiles(expression) {
    // generateFunctionFromString's own special-casing, mirrored.
    const safe = /^[\n\s]*if.*\(.*\)/.test(expression.trim())
        || /^(let|const)\s/.test(expression.trim())
        ? `(async()=>{ ${expression} })()`
        : expression;
    try {
        new AsyncFunction(
            ["__self", "scope"],
            `with (scope) { __self.result = ${safe} }; __self.finished = true; return __self.result;`,
        );
        return null;
    } catch (error) {
        return error.message;
    }
}

const ATTRIBUTE = /(\sx-[\w:.-]+|\s@[\w:.@-]+|\s:[\w:.-]+)="([^"]*)"/g;

test("every Alpine expression in every template compiles", () => {
    const broken = [];
    for (const file of htmlFiles(TEMPLATE_ROOT)) {
        const source = readFileSync(file, "utf8");
        for (const [, rawName, rawValue] of source.matchAll(ATTRIBUTE)) {
            const name = rawName.trim();
            if (!isAlpineExpression(name) || !rawValue.trim()) continue;
            for (const rendering of renderings(rawValue)) {
                const expression = compilable(name, rendering).trim();
                if (!expression) continue;
                const failure = compiles(expression);
                if (!failure) continue;
                const line = source.slice(0, source.indexOf(rawValue)).split("\n").length;
                broken.push(`${relative(TEMPLATE_ROOT, file)}:${line} ${name} — ${failure}`);
            }
        }
    }
    assert.deepEqual(broken, [], `\n${broken.join("\n")}\n`);
});
