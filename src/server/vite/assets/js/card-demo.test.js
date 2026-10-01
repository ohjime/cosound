import assert from "node:assert/strict";
import test from "node:test";

import { cardDemo } from "./card-demo.js";


function layers() {
    return [
        { sound_id: 1, sound_title: "Rain", gain: 70 },
        { sound_id: 2, sound_title: "Wind", gain: 95 },
    ];
}


test("the card demo normalizes UI state without adding audio data", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.currentLayer.sound_title, "Rain");
    assert.equal(demo.currentLayer.gain, 70);
    assert.equal(demo.currentLayer.mute, false);
    assert.equal("sound_file" in demo.currentLayer, false);
});


test("the blank card starts an unspecified layer at the centered gain", () => {
    const demo = cardDemo([{ sound_id: 1 }]);

    assert.equal(demo.currentLayer.gain, 50);
});


test("the fixed-palette demo exposes a continuous card hue", () => {
    const demo = cardDemo(layers());

    assert.equal("lightMode" in demo, false);
    assert.equal(demo.cardHue, 128);
    assert.equal(demo.colorName, "Green");

    demo.setCardHue(215);
    assert.equal(demo.cardHue, 215);
    assert.equal(demo.colorName, "Slate blue");

    demo.setCardHue(500);
    assert.equal(demo.cardHue, 360);
    assert.equal(demo.colorName, "Red");
});


test("card content customization starts blank with conservative visual defaults", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.flavorText, "");
    assert.equal(demo.flavorTextSize, 12);
    assert.equal(demo.indicatorText, "");
    assert.equal(demo.indicatorTextSize, 14);
    assert.equal(demo.indicatorCentered, false);
    assert.equal(demo.masterText, "COSOUND");
    assert.equal(demo.showLeftArrow, true);
    assert.equal(demo.showRightArrow, true);
    assert.equal(demo.showBottomArrow, true);
    assert.equal(demo.bottomArrowValue, 50);
    assert.equal(demo.uploadedArtworkUrl, "");
    assert.equal(demo.uploadedArtworkName, "");
    assert.equal(demo.artworkError, "");
    assert.equal(demo.showArtworkText, false);
    assert.equal(demo.artworkTitle, "");
    assert.equal(demo.artistName, "");
    assert.equal(demo.artworkTextSize, 18);
    assert.equal(demo.showLikeButton, false);
});


test("content sizes and the bottom-arrow value stay within their control ranges", () => {
    const demo = cardDemo(layers());
    const originalGains = demo.layers.map((layer) => layer.gain);

    demo.setFlavorTextSize(-1);
    assert.equal(demo.flavorTextSize, 8);
    demo.setFlavorTextSize(200);
    assert.equal(demo.flavorTextSize, 28);

    demo.setIndicatorTextSize(-1);
    assert.equal(demo.indicatorTextSize, 8);
    demo.setIndicatorTextSize(200);
    assert.equal(demo.indicatorTextSize, 24);

    demo.setArtworkTextSize(-1);
    assert.equal(demo.artworkTextSize, 8);
    demo.setArtworkTextSize(200);
    assert.equal(demo.artworkTextSize, 32);

    demo.setBottomArrowValue(-1);
    assert.equal(demo.bottomArrowValue, 0);
    demo.setBottomArrowValue(200);
    assert.equal(demo.bottomArrowValue, 100);
    assert.deepEqual(demo.layers.map((layer) => layer.gain), originalGains);
});


test("artwork uploads validate files and revoke every replaced object URL", () => {
    const demo = cardDemo(layers());
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const revoked = [];
    let objectUrlSequence = 0;

    URL.createObjectURL = () => `blob:card-demo-${objectUrlSequence += 1}`;
    URL.revokeObjectURL = (url) => revoked.push(url);

    try {
        assert.equal(demo.setArtwork({ name: "forest.png", type: "image/png", size: 1024 }), true);
        assert.equal(demo.uploadedArtworkUrl, "blob:card-demo-1");
        assert.equal(demo.uploadedArtworkName, "forest.png");
        assert.equal(demo.artworkError, "");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setArtwork({ name: "notes.txt", type: "text/plain", size: 32 }), false);
        assert.equal(demo.artworkError, "Choose an image file.");
        assert.equal(demo.uploadedArtworkUrl, "blob:card-demo-1");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setArtwork({ name: "huge.jpg", type: "image/jpeg", size: 10 * 1024 * 1024 + 1 }), false);
        assert.equal(demo.artworkError, "Choose an image smaller than 10 MB.");
        assert.equal(demo.uploadedArtworkUrl, "blob:card-demo-1");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setArtwork({ name: "lake.webp", type: "image/webp", size: 2048 }), true);
        assert.equal(demo.uploadedArtworkUrl, "blob:card-demo-2");
        assert.equal(demo.uploadedArtworkName, "lake.webp");
        assert.equal(demo.artworkError, "");
        assert.deepEqual(revoked, ["blob:card-demo-1"]);

        demo.destroy();
        assert.equal(demo.uploadedArtworkUrl, "");
        assert.equal(demo.uploadedArtworkName, "");
        assert.equal(demo.artworkError, "");
        assert.deepEqual(revoked, ["blob:card-demo-1", "blob:card-demo-2"]);

        demo.destroy();
        assert.deepEqual(revoked, ["blob:card-demo-1", "blob:card-demo-2"]);
    } finally {
        URL.createObjectURL = originalCreateObjectURL;
        URL.revokeObjectURL = originalRevokeObjectURL;
    }
});


test("card color is independent while ring and paper share one color", () => {
    const demo = cardDemo(layers());

    assert.deepEqual([demo.cardHue, demo.ringHue], [128, 128]);
    assert.equal("pageHue" in demo, false);

    demo.setCardHue(212);
    demo.setRingHue(32);

    assert.equal(demo.cardColorName, "Slate blue");
    assert.equal(demo.ringColorName, "Warm umber");
    assert.match(demo.editorStyle, /--card-hue: 212/);
    assert.match(demo.editorStyle, /--ring-hue: 32/);
    assert.doesNotMatch(demo.editorStyle, /--page-hue/);
});


test("the Letter sheet relays out cards as scale and gap change", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 3.5);
    assert.equal(demo.sheetColumns, 3);
    assert.equal(demo.sheetRows, 2);
    assert.equal(demo.sheetCount, 6);

    demo.setOverallScale(80);
    assert.equal(demo.effectiveCardWidthIn, 1.6);
    assert.equal(demo.effectiveCardHeightIn, 2.8);
    assert.equal(demo.sheetColumns, 4);
    assert.equal(demo.sheetRows, 3);
    assert.equal(demo.sheetCount, 12);

    demo.setOverallScale(100);
    demo.setCardGap(1.25);
    assert.equal(demo.sheetColumns, 2);
    assert.equal(demo.sheetRows, 2);
    assert.equal(demo.sheetCount, 4);
});


test("business-card dimensions and layout controls stay within print bounds", () => {
    const demo = cardDemo(layers());

    demo.setCardWidth(5);
    demo.setCardHeight(5);
    demo.setOverallScale(40);
    demo.setCardGap(-1);

    assert.equal(demo.cardWidthIn, 2);
    assert.equal(demo.cardHeightIn, 3.5);
    assert.equal(demo.overallScale, 80);
    assert.equal(demo.cardGapIn, 0);
    assert.match(demo.editorStyle, /--effective-card-width: 1\.6in/);
    assert.match(demo.editorStyle, /--effective-card-height: 2\.8/);
});


test("carousel controls stay within the available layers", () => {
    const demo = cardDemo(layers());

    demo.move(1);
    assert.equal(demo.currentIndex, 1);
    demo.move(1);
    assert.equal(demo.currentIndex, 1);
    demo.move(-2);
    assert.equal(demo.currentIndex, 0);
});


test("mute, isolate, and favorite controls update local UI state", () => {
    const demo = cardDemo(layers());

    demo.toggleMute(demo.currentLayer);
    assert.equal(demo.currentLayer.mute, true);
    assert.equal(demo.grayscaleFor(demo.currentLayer), 100);

    demo.toggleIsolate(demo.layers[1]);
    assert.equal(demo.layers[1].isolated, true);
    assert.equal(demo.layers[0].mute, true);

    demo.toggleFavorite(demo.layers[1]);
    assert.equal(demo.layers[1].saved, true);
});


test("layer and master volume controls clamp their UI values", () => {
    const demo = cardDemo(layers());

    demo.setCurrentGain(35);
    assert.equal(demo.currentLayer.gain, 35);
    assert.equal(demo.currentLayer.mute, false);

    demo.adjustAll(10);
    assert.deepEqual(demo.layers.map((layer) => layer.gain), [45, 100]);
    demo.adjustAll(-200);
    assert.deepEqual(demo.layers.map((layer) => layer.gain), [0, 0]);
});
