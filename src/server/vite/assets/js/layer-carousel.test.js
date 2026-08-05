import test from "node:test";
import assert from "node:assert/strict";

import { JUMP_TIMEOUT_MS, layerCarousel } from "./layer-carousel.js";

// The component only ever asks the DOM two things — where each item sits and
// where the strip is scrolled to — and only ever tells it one: scroll there. So
// the whole browser it needs is this.

const ITEM_WIDTH = 300;

function fakeCarousel(count) {
    const items = [];
    const el = {
        scrollLeft: 0,
        scrolls: [],
        getElementsByClassName(name) {
            return name === "carousel-item" ? items : [];
        },
        scrollTo({ left, behavior }) {
            el.scrolls.push({ left, behavior });
        },
        /** What `x-for` does when a layer is added: one more item to measure. */
        addItem() {
            items.push({ offsetLeft: items.length * ITEM_WIDTH });
        },
        /** Where a scroll animation has got to, in items. */
        at(index) {
            el.scrollLeft = index * ITEM_WIDTH;
        },
    };
    for (let i = 0; i < count; i++) el.addItem();
    return el;
}

/**
 * Stand the component up the way Alpine would: the magics it reads are plain
 * properties on the object, and $nextTick is drained by hand so a test can look
 * at the state a click left behind *before* the scroll it queued goes out.
 */
function mount(count) {
    const store = {
        layers: Array.from({ length: count }, (_, i) => ({ sound_id: `s${i}` })),
        currentIndex: 0,
    };
    const el = fakeCarousel(count);
    const ticks = [];
    const carousel = layerCarousel("soundLayers");
    carousel.$store = { soundLayers: store };
    carousel.$refs = { carousel: el };
    carousel.$nextTick = (fn) => ticks.push(fn);
    return {
        carousel,
        store,
        el,
        flush() {
            while (ticks.length) ticks.shift()();
        },
    };
}

test("a jump selects its target before the artwork has moved", () => {
    const { carousel, store, el, flush } = mount(8);

    carousel.select(7);

    assert.equal(store.currentIndex, 7, "the pill should light up on the click");
    assert.deepEqual(el.scrolls, [], "and the scroll should wait for the tick");

    flush();
    assert.deepEqual(el.scrolls, [{ left: 7 * ITEM_WIDTH, behavior: "smooth" }]);
});

test("a jump does not walk the selection through the layers it scrolls past", () => {
    const { carousel, store, el, flush } = mount(8);
    carousel.select(7);
    flush();

    for (const passing of [1, 2, 3, 4, 5, 6]) {
        el.at(passing);
        carousel.updateActive();
        assert.equal(store.currentIndex, 7, `layer ${passing} is scenery, not a choice`);
    }

    el.at(7);
    carousel.updateActive();
    assert.equal(store.currentIndex, 7);
    assert.equal(carousel.jumpingTo, null, "arriving ends the wait");
});

test("swiping the artwork moves the selection live", () => {
    const { carousel, store, el } = mount(4);

    for (const index of [1, 2, 3, 2]) {
        el.at(index);
        carousel.updateActive();
        assert.equal(store.currentIndex, index);
    }
});

test("the selection follows the scroll again once a jump has landed", () => {
    const { carousel, store, el, flush } = mount(5);
    carousel.select(4);
    flush();
    el.at(4);
    carousel.updateActive();

    el.at(1);
    carousel.updateActive();
    assert.equal(store.currentIndex, 1);
});

test("a hand on the artwork cuts a jump short and takes over", () => {
    const { carousel, store, el, flush } = mount(6);
    carousel.select(5);
    flush();
    el.at(2);
    carousel.updateActive();
    assert.equal(store.currentIndex, 5);

    // What @pointerdown / @touchstart / @wheel fire.
    carousel.release();

    el.at(2);
    carousel.updateActive();
    assert.equal(store.currentIndex, 2, "the swipe decides now, not the jump");
});

test("choosing the layer already showing leaves nothing pending", () => {
    const { carousel, store, el, flush } = mount(3);

    carousel.select(0);
    flush();

    assert.deepEqual(el.scrolls, [], "there is nowhere to scroll to");
    assert.equal(carousel.jumpingTo, null);

    el.at(1);
    carousel.updateActive();
    assert.equal(store.currentIndex, 1, "and the strip is not frozen");
});

test("a jump the browser never runs stops being waited on", (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const { carousel, store, el, flush } = mount(4);
    carousel.select(3);
    flush();

    // The scroll went out and simply never happened — reduced motion, a hidden
    // strip, a browser that ignored it.
    t.mock.timers.tick(JUMP_TIMEOUT_MS);
    assert.equal(carousel.jumpingTo, null);

    el.at(1);
    carousel.updateActive();
    assert.equal(store.currentIndex, 1);
});

test("a layer added in the same breath is selected before its item exists", () => {
    const { carousel, store, el, flush } = mount(3);

    // What the pill's `+` does: the store grows, then asks to be taken there,
    // all before x-for has drawn the item.
    store.layers.push({ sound_id: "s3" });
    carousel.select(3);
    assert.equal(store.currentIndex, 3, "the store is the truth, not the markup");

    el.addItem();
    flush();
    assert.deepEqual(el.scrolls, [{ left: 3 * ITEM_WIDTH, behavior: "smooth" }]);
});

test("an index past the end of the mix lands on the last layer", () => {
    const { carousel, store, flush } = mount(3);

    carousel.select(99);
    flush();
    assert.equal(store.currentIndex, 2);

    carousel.select(-4);
    flush();
    assert.equal(store.currentIndex, 0);
});

test("the arrows step from wherever the selection currently is", () => {
    const { carousel, store, flush } = mount(4);

    carousel.move(1);
    flush();
    assert.equal(store.currentIndex, 1);

    // Pressed again before the first scroll has arrived: it steps from the
    // layer already chosen, not from the one still on screen.
    carousel.move(1);
    flush();
    assert.equal(store.currentIndex, 2);

    carousel.move(-1);
    flush();
    assert.equal(store.currentIndex, 1);
});

test("the carousel opens on the layer the store is already holding", () => {
    const { carousel, store, el } = mount(5);
    store.currentIndex = 3;
    el.at(3);

    carousel.start();

    assert.deepEqual(el.scrolls, [{ left: 3 * ITEM_WIDTH, behavior: "instant" }]);
    assert.equal(store.currentIndex, 3);
    assert.equal(carousel.jumpingTo, null);
});

test("an empty mix is not something to scroll around in", () => {
    const { carousel, store, el, flush } = mount(0);

    carousel.select(0);
    carousel.move(1);
    flush();
    carousel.updateActive();
    carousel.start();

    assert.deepEqual(el.scrolls, []);
    assert.equal(store.currentIndex, 0);
});
