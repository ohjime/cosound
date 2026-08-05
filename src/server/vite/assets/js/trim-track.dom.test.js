import test from "node:test";
import assert from "node:assert/strict";

import { trimTrack } from "./trim-track.js";

// The panel builds its own inside and moves it by hand, so the only way to test
// what it does is to give it something to build into. This is the slice of the
// DOM it actually touches — enough to mount it, drag it and read back where the
// markers landed, without pulling in a browser.

class FakeElement {
    constructor(tag) {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.parentElement = null;
        this.style = {};
        this.dataset = {};
        this.attributes = {};
        this.className = "";
        this.textContent = "";
        this.tabIndex = -1;
        this.listeners = {};
        // Laid out by the test, the way a browser would have.
        this.clientWidth = 0;
        this.clientHeight = 0;
        this.offsetWidth = 0;
        this.classList = {
            add: (...names) => {
                this.className += ` ${names.join(" ")}`;
            },
        };
    }

    append(...kids) {
        for (const kid of kids) {
            kid.parentElement = this;
            this.children.push(kid);
        }
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        return this.attributes[name];
    }

    addEventListener(name, handler) {
        (this.listeners[name] ??= []).push(handler);
    }

    /** Fire a listener the component registered, as the browser would. */
    fire(name, event = {}) {
        for (const handler of this.listeners[name] ?? []) {
            handler({ target: this, button: 0, preventDefault() {}, ...event });
        }
    }

    closest(selector) {
        const key = selector.replace(/^\[data-|]$/g, "").replace(/-(\w)/g, (_, c) => c.toUpperCase());
        for (let node = this; node; node = node.parentElement) {
            if (node.dataset[key] !== undefined) return node;
        }
        return null;
    }

    getBoundingClientRect() {
        return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight };
    }

    getContext() {
        return {
            fillStyle: null,
            setTransform() {},
            clearRect() {},
            fillRect() {},
            createLinearGradient: () => ({ addColorStop() {} }),
        };
    }

    focus() {}
    setPointerCapture() {}
}

let pending = null;

function mount({ width = 400, height = 128, playheads = null } = {}) {
    globalThis.document = { createElement: (tag) => new FakeElement(tag) };
    globalThis.ResizeObserver = class {
        observe() {}
        disconnect() {}
    };
    globalThis.devicePixelRatio = 1;
    // The playhead sweep runs off rAF. Hold the callback instead of running it,
    // so a test can step the sweep exactly when it wants to.
    globalThis.requestAnimationFrame = (fn) => {
        pending = fn;
        return 1;
    };
    globalThis.cancelAnimationFrame = () => {
        pending = null;
    };

    // The engine the panel reaches for its peaks and its playheads.
    globalThis.cosoundMixer = playheads
        ? { layerPlayheads: () => playheads() }
        : undefined;

    const root = new FakeElement("div");
    const commits = [];
    const panel = trimTrack();
    panel.$el = root;
    panel.$dispatch = (name, detail) => commits.push({ name, detail });
    panel.init();

    const screen = root.children[0];
    screen.clientWidth = width;
    screen.clientHeight = height;
    const handles = {};
    // The playheads are the divs with a tick but no marker name on them.
    const heads = [];
    for (const child of screen.children) {
        if (child.dataset.trimHandle) handles[child.dataset.trimHandle] = child;
        else if (child.className.includes("flex-col")) heads.push(child);
    }
    /** Run one frame of the playhead sweep. */
    const sweep = () => pending?.();
    // `x` is a pixel across the panel; the component reads clientX off the event.
    const press = (x, target = screen) => screen.fire("pointerdown", { clientX: x, target, pointerId: 1 });
    const moveTo = (x) => screen.fire("pointermove", { clientX: x, pointerId: 1 });
    const release = () => screen.fire("pointerup", { pointerId: 1 });
    return { panel, root, screen, handles, heads, commits, press, moveTo, release, sweep };
}

const lastDetail = (commits) => commits.at(-1)?.detail;

// Percentages are set straight from the arithmetic, so `20%` can arrive as
// `19.999999999999996%`. CSS does not care and neither does this.
function assertPercent(actual, expected, what) {
    assert.ok(
        Math.abs(Number.parseFloat(actual) - expected) < 1e-6,
        `${what}: expected ~${expected}%, got ${actual}`,
    );
}

test("the markers sit where the crop says", () => {
    const { panel, screen, handles } = mount();
    panel.load({ src: "", duration: 10, start: 2, end: 8 });
    assertPercent(handles.start.style.left, 20, "start marker");
    assertPercent(handles.end.style.left, 80, "end marker");
    // What is cut is shaded from either edge, not drawn out of the wave.
    assertPercent(screen.children[1].style.width, 20, "head shade");
    assertPercent(screen.children[2].style.width, 20, "tail shade");
});

test("a null end means the tail of the file", () => {
    const { panel, handles } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    assertPercent(handles.end.style.left, 100, "end marker");
    assert.equal(handles.end.getAttribute("aria-valuenow"), "10.000");
});

test("pressing empty track sends the nearer marker there, and commits on release", () => {
    const { panel, commits, press, release } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(100); // a quarter across: 2.5s, nearer the start than the end
    assert.deepEqual(commits, [], "a press alone must not rebuild the voice");
    release();
    assert.deepEqual(lastDetail(commits), { trim_start: 2.5, trim_end: null });
});

test("a drag is one commit however far it is dragged", () => {
    const { panel, commits, press, moveTo, release } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(40);
    moveTo(80);
    moveTo(120);
    moveTo(160);
    release();
    assert.equal(commits.length, 1);
    assert.deepEqual(lastDetail(commits), { trim_start: 4, trim_end: null });
});

test("an end marker off the tail commits a real number", () => {
    const { panel, commits, press, moveTo, release } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(320); // 8s, nearer the end
    moveTo(280); // 7s
    release();
    assert.deepEqual(lastDetail(commits), { trim_start: 0, trim_end: 7 });
});

test("the markers refuse to cross, a playable region apart", () => {
    const { panel, handles, commits, press, moveTo, release } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(0, handles.start);
    moveTo(400); // dragged onto the end marker
    release();
    // MIN_REGION_SECONDS short of it, which is the shortest crop the engine plays.
    assert.deepEqual(lastDetail(commits), { trim_start: 9.75, trim_end: null });
});

test("grabbing a marker does not make it jump to the press", () => {
    const { panel, handles, commits, press, release } = mount();
    panel.load({ src: "", duration: 10, start: 3, end: 8 });
    // Pressing the start marker slightly off-centre, as a finger does.
    press(126, handles.start);
    release();
    assert.deepEqual(lastDetail(commits), { trim_start: 3, trim_end: 8 });
});

test("each marker nudges from the keyboard and commits", () => {
    const { panel, handles, commits } = mount();
    panel.load({ src: "", duration: 10, start: 1, end: 9 });
    handles.start.fire("keydown", { key: "ArrowRight" });
    assert.deepEqual(lastDetail(commits), { trim_start: 1.05, trim_end: 9 });
    handles.end.fire("keydown", { key: "ArrowLeft", shiftKey: true });
    assert.deepEqual(lastDetail(commits), { trim_start: 1.05, trim_end: 8.5 });
    handles.end.fire("keydown", { key: "End" });
    assert.deepEqual(lastDetail(commits), { trim_start: 1.05, trim_end: null });
});

test("a key the panel has no use for is left to the page", () => {
    const { panel, handles, commits } = mount();
    panel.load({ src: "", duration: 10, start: 1, end: 9 });
    handles.start.fire("keydown", { key: "Tab" });
    assert.deepEqual(commits, []);
});

test("the store cannot move a marker out from under a drag", () => {
    const { panel, handles, press, moveTo, release } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(200);
    moveTo(240);
    // The engine writing an analysis back mid-gesture, which it does whenever
    // anything else about the layer changes.
    panel.load({ src: "", duration: 10, start: 0, end: null });
    assertPercent(handles.start.style.left, 60, "the drag owns the marker");
    release();
    // And once the gesture is over, the store is in charge again.
    panel.load({ src: "", duration: 10, start: 1, end: 4 });
    assertPercent(handles.start.style.left, 10, "start marker");
    assertPercent(handles.end.style.left, 40, "end marker");
});

test("a layer with no audio says so instead of drawing an empty panel", () => {
    const { panel, screen } = mount();
    panel.load({ src: "", duration: 0, start: 0, end: null });
    const note = screen.children.find((child) => child.tagName === "P");
    assert.equal(note.textContent, "No sound on this layer yet.");
});

test("a playhead sweeps to wherever the engine says the voice is", () => {
    let at = [1];
    const { panel, heads, sweep } = mount({ playheads: () => at });
    panel.load({ src: "", duration: 10, start: 0, end: null, index: 0 });
    sweep();
    assert.equal(heads[0].style.display, "");
    assertPercent(heads[0].style.left, 10, "playhead");
    assert.equal(heads[0].children[0].textContent, "0:01.000");
    at = [7.5];
    sweep();
    assertPercent(heads[0].style.left, 75, "playhead");
    assert.equal(heads[0].children[0].textContent, "0:07.500");
});

test("both drifting passes get a playhead, and only the sounding ones", () => {
    let at = [2, 6];
    const { panel, heads, sweep } = mount({ playheads: () => at });
    panel.load({ src: "", duration: 10, start: 0, end: null, index: 0 });
    sweep();
    assertPercent(heads[0].style.left, 20, "pass A");
    assertPercent(heads[1].style.left, 60, "pass B");
    // Between passes the drift is a gap, not a loop: the head goes away rather
    // than parking somewhere it is not playing.
    at = [2];
    sweep();
    assert.equal(heads[0].style.display, "");
    assert.equal(heads[1].style.display, "none");
    at = [];
    sweep();
    assert.equal(heads[0].style.display, "none");
});

test("a crossfading layer can show every pass that is sounding", () => {
    // Both schedules sound twice over while a loop crossfade runs — one pass
    // leaving the tail under the next arriving at the head — so the panel keeps
    // four slots and the engine says which of them are in use.
    const { panel, heads, sweep } = mount({ playheads: () => [9.5, 0.5, 4.5, 7] });
    panel.load({ src: "", duration: 10, start: 0, end: null, index: 0 });
    sweep();

    assert.equal(heads.length, 4);
    assertPercent(heads[0].style.left, 95, "A running out its tail");
    assertPercent(heads[1].style.left, 5, "A arriving at its head");
    assertPercent(heads[3].style.left, 70, "B");
});

test("with no voice to ask, the panel simply shows no playhead", () => {
    const { panel, heads, sweep } = mount();
    panel.load({ src: "", duration: 10, start: 0, end: null });
    sweep();
    assert.equal(heads[0].style.display, "none");
    assert.equal(heads[1].style.display, "none");
});

test("the sweep stops when the panel goes away", () => {
    const { panel, sweep } = mount({ playheads: () => [1] });
    panel.load({ src: "", duration: 10, start: 0, end: null, index: 0 });
    sweep();
    panel.destroy();
    assert.equal(pending, null, "a torn-down panel must not keep asking for frames");
});

test("a panel with no width yet neither draws nor throws", () => {
    const { panel, commits, press } = mount({ width: 0, height: 0 });
    panel.load({ src: "", duration: 10, start: 0, end: null });
    press(100);
    assert.deepEqual(commits, []);
});
