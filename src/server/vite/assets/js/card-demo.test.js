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
    assert.equal(demo.cardBrightness, 18.4);
    assert.equal(demo.ringBrightness, 20);
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
    assert.equal(demo.flavorOverlayUrl, "");
    assert.equal(demo.flavorOverlayName, "");
    assert.equal(demo.flavorOverlayError, "");
    assert.equal(demo.flavorOverlayTintHue, 128);
    assert.equal(demo.flavorOverlayTintBrightness, 50);
    assert.equal(demo.flavorOverlayTintStrength, 0);
    assert.equal(demo.indicatorText, "");
    assert.equal(demo.indicatorTextSize, 14);
    assert.equal(demo.indicatorTextSpacing, 0);
    assert.equal(demo.indicatorCentered, false);
    assert.equal(demo.masterText, "COSOUND");
    assert.equal(demo.masterTextSize, 12);
    assert.equal(demo.masterTextSpacing, 2.2);
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


test("flavor overlays validate images and revoke every replaced object URL", () => {
    const demo = cardDemo(layers());
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const revoked = [];
    let objectUrlSequence = 0;

    URL.createObjectURL = () => `blob:flavor-overlay-${objectUrlSequence += 1}`;
    URL.revokeObjectURL = (url) => revoked.push(url);

    try {
        assert.equal(demo.setFlavorOverlay({ name: "flourish.svg", type: "image/svg+xml", size: 1024 }), true);
        assert.equal(demo.flavorOverlayUrl, "blob:flavor-overlay-1");
        assert.equal(demo.flavorOverlayName, "flourish.svg");
        assert.equal(demo.flavorOverlayError, "");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setFlavorOverlay({ name: "notes.txt", type: "text/plain", size: 32 }), false);
        assert.equal(demo.flavorOverlayError, "Choose an image file.");
        assert.equal(demo.flavorOverlayUrl, "blob:flavor-overlay-1");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setFlavorOverlay({ name: "huge.png", type: "image/png", size: 10 * 1024 * 1024 + 1 }), false);
        assert.equal(demo.flavorOverlayError, "Choose an image smaller than 10 MB.");
        assert.equal(demo.flavorOverlayUrl, "blob:flavor-overlay-1");
        assert.deepEqual(revoked, []);

        assert.equal(demo.setFlavorOverlay({ name: "texture.png", type: "image/png", size: 2048 }), true);
        assert.equal(demo.flavorOverlayUrl, "blob:flavor-overlay-2");
        assert.equal(demo.flavorOverlayName, "texture.png");
        assert.equal(demo.flavorOverlayError, "");
        assert.deepEqual(revoked, ["blob:flavor-overlay-1"]);

        demo.clearFlavorOverlay();
        assert.equal(demo.flavorOverlayUrl, "");
        assert.equal(demo.flavorOverlayName, "");
        assert.equal(demo.flavorOverlayError, "");
        assert.deepEqual(revoked, ["blob:flavor-overlay-1", "blob:flavor-overlay-2"]);

        demo.clearFlavorOverlay();
        assert.deepEqual(revoked, ["blob:flavor-overlay-1", "blob:flavor-overlay-2"]);
    } finally {
        URL.createObjectURL = originalCreateObjectURL;
        URL.revokeObjectURL = originalRevokeObjectURL;
    }
});


test("appearance controls stay within their advertised ranges", () => {
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

    demo.setIndicatorTextSpacing(-200);
    assert.equal(demo.indicatorTextSpacing, -1);
    demo.setIndicatorTextSpacing(200);
    assert.equal(demo.indicatorTextSpacing, 8);

    demo.setMasterTextSize(-1);
    assert.equal(demo.masterTextSize, 8);
    demo.setMasterTextSize(200);
    assert.equal(demo.masterTextSize, 24);

    demo.setMasterTextSpacing(-200);
    assert.equal(demo.masterTextSpacing, -1);
    demo.setMasterTextSpacing(200);
    assert.equal(demo.masterTextSpacing, 8);

    demo.setCardBrightness(-1);
    assert.equal(demo.cardBrightness, 0);
    demo.setCardBrightness(200);
    assert.equal(demo.cardBrightness, 100);

    demo.setRingBrightness(-1);
    assert.equal(demo.ringBrightness, 0);
    demo.setRingBrightness(200);
    assert.equal(demo.ringBrightness, 100);

    demo.setFlavorOverlayTintHue(-1);
    assert.equal(demo.flavorOverlayTintHue, 0);
    demo.setFlavorOverlayTintHue(500);
    assert.equal(demo.flavorOverlayTintHue, 360);

    demo.setFlavorOverlayTintBrightness(-1);
    assert.equal(demo.flavorOverlayTintBrightness, 0);
    demo.setFlavorOverlayTintBrightness(200);
    assert.equal(demo.flavorOverlayTintBrightness, 100);

    demo.setFlavorOverlayTintStrength(-1);
    assert.equal(demo.flavorOverlayTintStrength, 0);
    demo.setFlavorOverlayTintStrength(200);
    assert.equal(demo.flavorOverlayTintStrength, 100);

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

    assert.deepEqual([demo.cardHue, demo.cardBrightness, demo.ringHue, demo.ringBrightness], [128, 18.4, 128, 20]);
    assert.equal("pageHue" in demo, false);

    demo.setCardHue(212);
    demo.setCardBrightness(42);
    demo.setRingHue(32);
    demo.setRingBrightness(64);

    assert.equal(demo.cardColorName, "Slate blue");
    assert.equal(demo.ringColorName, "Warm umber");
    assert.match(demo.editorStyle, /--card-hue: 212/);
    assert.match(demo.editorStyle, /--card-brightness: 42%/);
    assert.match(demo.editorStyle, /--ring-hue: 32/);
    assert.match(demo.editorStyle, /--ring-brightness: 64%/);
    assert.doesNotMatch(demo.editorStyle, /--page-hue/);
});


test("the flavor overlay tint follows the uploaded image alpha and remains independently adjustable", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.flavorOverlayTintStyle, "");
    demo.flavorOverlayUrl = "blob:transparent-logo";
    demo.setFlavorOverlayTintHue(215);
    demo.setFlavorOverlayTintBrightness(62);
    demo.setFlavorOverlayTintStrength(70);

    assert.equal(demo.flavorOverlayTintName, "Slate blue");
    assert.match(demo.flavorOverlayTintStyle, /background-color: hsl\(215 75% 62%\)/);
    assert.match(demo.flavorOverlayTintStyle, /opacity: 0\.7/);
    assert.match(demo.flavorOverlayTintStyle, /mask-image: url\("blob:transparent-logo"\)/);
    assert.match(demo.flavorOverlayTintStyle, /mask-position: center/);
    assert.match(demo.flavorOverlayTintStyle, /mask-size: contain/);
});


test("the Letter sheet relays out cards as scale and gap change", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 3.5);
    assert.equal(demo.maximumCardWidthIn, 8.5);
    assert.equal(demo.maximumCardHeightIn, 11);
    assert.equal(demo.islandPaddingXIn, 0.25);
    assert.equal(demo.islandPaddingYIn, 0.25);
    assert.equal(demo.sheetColumns, 3);
    assert.equal(demo.sheetRows, 2);
    assert.equal(demo.sheetCount, 6);

    demo.setOverallScale(80);
    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 3.5);
    assert.equal(demo.printedCardWidthIn, 1.6);
    assert.equal(demo.printedCardHeightIn, 2.8);
    assert.equal(demo.minimumCardWidthIn, 1.5);
    assert.equal(demo.maximumCardWidthIn, 8.5);
    assert.equal(demo.minimumCardHeightIn, 3.13);
    assert.equal(demo.maximumCardHeightIn, 11);
    assert.equal(demo.islandPaddingXIn, 0.25);
    assert.equal(demo.islandPaddingYIn, 0.25);
    assert.equal(demo.sheetColumns, 4);
    assert.equal(demo.sheetRows, 3);
    assert.equal(demo.sheetCount, 12);

    demo.setCardWidth(1.75);
    demo.setCardHeight(3.25);
    assert.equal(demo.effectiveCardWidthIn, 1.75);
    assert.equal(demo.effectiveCardHeightIn, 3.25);
    assert.equal(demo.printedCardWidthIn, 1.4);
    assert.equal(demo.printedCardHeightIn, 2.6);

    demo.setOverallScale(100);
    demo.setCardWidth(2);
    demo.setCardHeight(3.5);
    demo.setCardGap(1.25);
    assert.equal(demo.sheetColumns, 2);
    assert.equal(demo.sheetRows, 2);
    assert.equal(demo.sheetCount, 4);
});


test("overall scale covers 50 through 200 percent", () => {
    const demo = cardDemo(layers());

    demo.setOverallScale(50);
    assert.equal(demo.overallScale, 50);
    assert.equal(demo.scaleRatio, 0.5);
    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 3.5);
    assert.equal(demo.printedCardWidthIn, 1);
    assert.equal(demo.printedCardHeightIn, 1.75);
    assert.match(demo.editorStyle, /--card-scale: 0\.5;/);

    demo.setOverallScale(200);
    assert.equal(demo.overallScale, 200);
    assert.equal(demo.scaleRatio, 2);
    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 3.5);
    assert.equal(demo.printedCardWidthIn, 4);
    assert.equal(demo.printedCardHeightIn, 7);
    assert.match(demo.editorStyle, /--card-scale: 2;/);
    assert.match(demo.editorStyle, /--effective-card-width: 2in/);
    assert.match(demo.editorStyle, /--printed-card-width: 4in/);

    demo.setOverallScale(-999);
    assert.equal(demo.overallScale, 50);
    demo.setOverallScale(999);
    assert.equal(demo.overallScale, 200);
});


test("the card gap is also the colored island's outer cutting space", () => {
    const demo = cardDemo(layers());

    demo.setCardGap(0.6);
    assert.equal(demo.islandPaddingXIn, 0.6);
    assert.equal(demo.islandPaddingYIn, 0.6);
    assert.match(demo.editorStyle, /--island-padding-x: 0\.6in/);
    assert.match(demo.editorStyle, /--island-padding-y: 0\.6in/);
    assert.match(demo.editorStyle, /--card-gap: 0\.6in/);

    demo.setCardGap(0);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.equal(demo.islandPaddingYIn, 0);
});


test("width derives a reversible minimum height while preserving valid chosen heights", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.minimumCardHeightIn, 3.13);
    demo.setCardHeight(6);
    demo.setCardWidth(4);
    assert.equal(demo.effectiveCardWidthIn, 4);
    assert.equal(demo.minimumCardHeightIn, 5.13);
    assert.equal(demo.effectiveCardHeightIn, 6);

    demo.setCardWidth(6);
    assert.equal(demo.effectiveCardWidthIn, 6);
    assert.equal(demo.minimumCardHeightIn, 7.13);
    assert.equal(demo.effectiveCardHeightIn, 7.13);

    demo.setCardWidth(3);
    assert.equal(demo.effectiveCardWidthIn, 3);
    assert.equal(demo.minimumCardHeightIn, 4.13);
    assert.equal(demo.effectiveCardHeightIn, 6);

    demo.setCardHeight(-999);
    assert.equal(demo.effectiveCardWidthIn, 3);
    assert.equal(demo.effectiveCardHeightIn, 4.13);
});


test("card dimensions remain within the printable Letter bounds", () => {
    const demo = cardDemo(layers());

    demo.setCardWidth(999);
    assert.equal(demo.effectiveCardWidthIn, 8.5);
    assert.equal(demo.minimumCardHeightIn, 9.63);
    assert.equal(demo.effectiveCardHeightIn, 9.63);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.equal(demo.islandPaddingYIn, 0.25);

    demo.setCardHeight(999);
    assert.equal(demo.effectiveCardWidthIn, 8.5);
    assert.equal(demo.effectiveCardHeightIn, 11);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.equal(demo.islandPaddingYIn, 0);
    assert.match(demo.editorStyle, /--effective-card-width: 8\.5in/);
    assert.match(demo.editorStyle, /--effective-card-height: 11in/);
    assert.match(demo.editorStyle, /--island-padding-x: 0in/);
    assert.match(demo.editorStyle, /--island-padding-y: 0in/);

    demo.setCardWidth(4);
    assert.equal(demo.effectiveCardWidthIn, 4);
    assert.equal(demo.effectiveCardHeightIn, 11);
    assert.equal(demo.islandPaddingXIn, 0.25);
    assert.equal(demo.islandPaddingYIn, 0);

    demo.setCardHeight(6);
    assert.equal(demo.effectiveCardWidthIn, 4);
    assert.equal(demo.effectiveCardHeightIn, 6);
    assert.equal(demo.islandPaddingXIn, 0.25);
    assert.equal(demo.islandPaddingYIn, 0.25);
    assert.equal("cardScaleX" in demo, false);
    assert.equal("cardScaleY" in demo, false);
    assert.doesNotMatch(demo.editorStyle, /--card-scale-/);
});


test("the colored island padding shrinks only along an axis occupied by an oversized card", () => {
    const demo = cardDemo(layers());

    demo.setCardWidth(8.25);
    assert.equal(demo.effectiveCardWidthIn, 8.25);
    assert.equal(demo.minimumCardHeightIn, 9.38);
    assert.equal(demo.effectiveCardHeightIn, 9.38);
    assert.equal(demo.islandPaddingXIn, 0.125);
    assert.equal(demo.islandPaddingYIn, 0.25);

    demo.setCardWidth(2);
    demo.setCardHeight(10.75);
    assert.equal(demo.effectiveCardWidthIn, 2);
    assert.equal(demo.effectiveCardHeightIn, 10.75);
    assert.equal(demo.islandPaddingXIn, 0.25);
    assert.equal(demo.islandPaddingYIn, 0.125);
});


test("scale magnifies the card without moving its layout minimums", () => {
    const demo = cardDemo(layers());

    demo.setOverallScale(80);
    assert.equal(demo.minimumCardWidthIn, 1.5);
    assert.equal(demo.minimumCardHeightIn, 3.13);

    demo.setCardWidth(-999);
    assert.equal(demo.effectiveCardWidthIn, 1.5);
    assert.equal(demo.printedCardWidthIn, 1.2);
    assert.equal(demo.minimumCardHeightIn, 2.63);
    assert.equal(demo.effectiveCardHeightIn, 3.5);

    demo.setCardHeight(-999);
    assert.equal(demo.effectiveCardWidthIn, 1.5);
    assert.equal(demo.effectiveCardHeightIn, 2.63);
    assert.equal(demo.printedCardHeightIn, 2.104);
});


test("the printed card never outgrows the Letter sheet at any scale", () => {
    const demo = cardDemo(layers());

    demo.setOverallScale(200);
    assert.equal(demo.maximumCardWidthIn, 4.25);
    assert.equal(demo.maximumCardHeightIn, 5.5);

    demo.setCardWidth(999);
    assert.equal(demo.effectiveCardWidthIn, 4.25);
    assert.equal(demo.printedCardWidthIn, 8.5);
    assert.equal(demo.minimumCardHeightIn, 5.38);
    assert.equal(demo.effectiveCardHeightIn, 5.38);
    assert.equal(demo.printedCardHeightIn, 10.76);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.equal(demo.islandPaddingYIn, 0.12);

    demo.setCardHeight(999);
    assert.equal(demo.effectiveCardHeightIn, 5.5);
    assert.equal(demo.printedCardHeightIn, 11);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.equal(demo.islandPaddingYIn, 0);
    assert.match(demo.editorStyle, /--printed-card-width: 8\.5in/);
    assert.match(demo.editorStyle, /--printed-card-height: 11in/);
    assert.match(demo.editorStyle, /--island-padding-x: 0in/);
    assert.match(demo.editorStyle, /--island-padding-y: 0in/);

    demo.setCardGap(999);
    assert.equal(demo.cardGapIn, 1.25);
    assert.equal(demo.sheetColumns, 1);
    assert.equal(demo.sheetRows, 1);
    assert.equal(demo.sheetCount, 1);

    demo.setOverallScale(100);
    assert.equal(demo.effectiveCardWidthIn, 4.25);
    assert.equal(demo.printedCardWidthIn, 4.25);
});


test("the print guide keeps its paper size and stays centered on the middle top-row card", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.showGuide, true);
    assert.equal(demo.guideWidthIn, 2);
    assert.equal(demo.guideHeightIn, 3.5);
    assert.equal(demo.sheetColumns, 3);
    assert.equal(demo.guideColumn, 1);
    assert.equal(demo.guideCenterXIn, 4.25);
    assert.equal(demo.guideCenterYIn, 3.625);
    assert.match(demo.editorStyle, /--guide-width: 2in/);
    assert.match(demo.editorStyle, /--guide-height: 3\.5in/);
    assert.match(demo.editorStyle, /--guide-center-x: 4\.25in/);
    assert.match(demo.editorStyle, /--guide-center-y: 3\.625in/);

    demo.setGuideWidth(4);
    demo.setGuideHeight(4);
    demo.setOverallScale(200);
    demo.setCardWidth(3);
    demo.setCardHeight(5);
    assert.equal(demo.guideWidthIn, 4);
    assert.equal(demo.guideHeightIn, 4);
    assert.equal(demo.sheetCount, 1);
    assert.equal(demo.guideColumn, 0);
    assert.equal(demo.guideCenterXIn, 4.25);
    assert.equal(demo.guideCenterYIn, 5.5);

    demo.setOverallScale(80);
    demo.setCardWidth(2);
    demo.setCardHeight(3.5);
    assert.equal(demo.sheetColumns, 4);
    assert.equal(demo.guideColumn, 1);
    assert.equal(demo.guideCenterXIn, 3.325);
    assert.equal(demo.guideWidthIn, 4);

    demo.setOverallScale(100);
    demo.setCardGap(0.5);
    assert.equal(demo.sheetColumns, 3);
    assert.equal(demo.sheetRows, 2);
    assert.equal(demo.guideCenterXIn, 4.25);
    assert.equal(demo.guideCenterYIn, 3.5);

    demo.setGuideWidth(-999);
    demo.setGuideHeight(999);
    assert.equal(demo.guideWidthIn, 0.25);
    assert.equal(demo.guideHeightIn, 11);
});


test("split printing turns one sheet into a top and a bottom layer with the same layout", () => {
    const demo = cardDemo(layers());

    assert.equal(demo.splitLayers, false);
    assert.deepEqual(demo.printSheets.map((sheet) => sheet.layer), ["full"]);

    const layout = [demo.sheetCount, demo.sheetColumns, demo.sheetRows, demo.editorStyle];
    demo.splitLayers = true;
    assert.deepEqual(demo.printSheets.map((sheet) => sheet.layer), ["top", "bottom"]);
    assert.deepEqual(
        demo.printSheets.map((sheet) => sheet.caption),
        ["Sheet 1 · Top layer · cut out the holes", "Sheet 2 · Bottom layer"],
    );
    assert.deepEqual([demo.sheetCount, demo.sheetColumns, demo.sheetRows, demo.editorStyle], layout);

    demo.splitLayers = false;
    assert.deepEqual(demo.printSheets.map((sheet) => sheet.layer), ["full"]);
    assert.equal(demo.printLayerStyle, "");
});


function decodeMask(url) {
    return decodeURIComponent(url.replace(/^url\("data:image\/svg\+xml,/, "").replace(/"\)$/, ""));
}


test("the bottom sheet's border color fills the island but leaves every card body bare", () => {
    const demo = cardDemo(layers());
    demo.splitLayers = true;

    const svg = decodeMask(demo.bottomSheetMask);
    assert.match(svg, /viewBox="0 0 7 7\.75"/);
    assert.match(svg, /fill-rule="evenodd"/);
    // The island outline, then one rounded body per card.
    assert.equal(svg.match(/M/g).length, demo.sheetCount + 1);
    assert.match(svg, /M0\.4375 0\.25H2\.0625A0\.1875 0\.1875/);
    assert.match(demo.printLayerStyle, /--bottom-sheet-mask: url\("data:image\/svg\+xml,/);
    assert.match(demo.printLayerStyle, /--top-cutout-mask: none/);

    demo.setOverallScale(50);
    demo.setCardGap(0);
    assert.equal(demo.islandPaddingXIn, 0);
    assert.match(decodeMask(demo.bottomSheetMask), /M0\.0938 0H0\.9063A0\.0938 0\.0938/);
});


function fakeElement(rect, { attributes = {}, children = {}, hidden = false } = {}) {
    return {
        offsetWidth: rect.width,
        offsetHeight: rect.height,
        getBoundingClientRect: () => ({ left: rect.x, top: rect.y, width: rect.width, height: rect.height }),
        getClientRects: () => (hidden ? [] : [rect]),
        getAttribute: (name) => attributes[name] ?? null,
        querySelector: (selector) => children[selector]?.[0] ?? null,
        querySelectorAll: (selector) => selector.split(", ").flatMap((part) => children[part] ?? []),
    };
}


test("top-sheet holes trace each bottom-sheet piece in the card's own unscaled pixels", () => {
    const glyph = (rect, turn) => {
        const path = fakeElement(rect, { attributes: { d: "M400-280v-400l200 200-200 200Z", "stroke-width": "40" } });
        const icon = fakeElement(rect, { attributes: { viewBox: "0 -960 960 960" }, children: { path: [path] } });
        icon.style = { rotate: turn };
        return icon;
    };
    // Laid out at 2x scale, 100px to the right of the viewport origin.
    const frame = fakeElement({ x: 148, y: 56, width: 288, height: 288 });
    frame.style = {
        boxShadow: "rgba(0, 0, 0, 0) 0px 0px 0px 0px, oklab(0.8 -0.02 -0.02 / 0.7) 0px 0px 0px 7px",
        borderTopLeftRadius: "6px",
        borderTopRightRadius: "6px",
        borderBottomRightRadius: "0px",
        borderBottomLeftRadius: "0px",
    };
    const track = fakeElement({ x: 232, y: 392, width: 120, height: 16 });
    track.style = { boxShadow: "none", borderTopLeftRadius: "3.35544e+07px", borderTopRightRadius: "3.35544e+07px", borderBottomRightRadius: "3.35544e+07px", borderBottomLeftRadius: "3.35544e+07px" };
    const hiddenControl = fakeElement({ x: 0, y: 0, width: 0, height: 0 }, { hidden: true });
    hiddenControl.style = { boxShadow: "none" };
    const bottomArrow = glyph({ x: 218, y: 300, width: 132, height: 80 }, "90deg");
    const card = fakeElement({ x: 100, y: 0, width: 384, height: 672 }, {
        children: {
            "[data-card-demo-artwork-frame]": [frame],
            "[data-card-demo-volume-track]": [track],
            "[data-card-demo-slider-control]": [hiddenControl],
            "[data-card-demo-bottom-arrow] svg": [bottomArrow],
        },
    });
    card.offsetWidth = 192;
    card.offsetHeight = 336;
    const root = { querySelector: (selector) => (selector === '[data-print-layer="top"] [data-core-card]' ? card : null) };

    const originalStyle = globalThis.getComputedStyle;
    globalThis.getComputedStyle = (element) => element.style ?? {};
    try {
        const demo = cardDemo(layers());
        demo.measureTopCutouts(root);
        const svg = decodeMask(demo.topCutoutMask);

        assert.match(svg, /viewBox="0 0 192 336"/);
        // The frame's ring is cut 7px wide around the artwork, which stays.
        assert.match(svg, /<path fill="black" d="M30 21H162A13 13 0 0 1 175 34V179A0 0 0 0 1 175 179H17A0 0 0 0 1 17 179V34A13 13 0 0 1 30 21Z"\/>/);
        assert.match(svg, /<path fill="white" d="M30 28H162A6 6 0 0 1 168 34V172A0 0 0 0 1 168 172H24A0 0 0 0 1 24 172V34A6 6 0 0 1 30 28Z"\/>/);
        // A pill keeps its round ends instead of the infinite Tailwind radius.
        assert.match(svg, /M70 196H122A4 4 0 0 1 126 200V200A4 4 0 0 1 122 204H70A4 4 0 0 1 66 200V200A4 4 0 0 1 70 196Z/);
        // Arrows keep their stretch and rotation.
        assert.match(svg, /<svg x="59" y="150" width="66" height="40" viewBox="0 -960 960 960" preserveAspectRatio="none"/);
        assert.match(svg, /transform="rotate\(90 480 -480\)"/);
        assert.match(svg, /stroke-width="40"/);
        assert.equal(svg.match(/fill="black"/g).length, 3);
        assert.match(demo.printLayerStyle, /^$/);
        demo.splitLayers = true;
        assert.match(demo.printLayerStyle, /--top-cutout-mask: url\("data:image\/svg\+xml,/);
    } finally {
        globalThis.getComputedStyle = originalStyle;
    }
});


test("dimension endpoints stay aligned to the hundredth-inch slider step", () => {
    const demo = cardDemo(layers());

    for (let scale = 50; scale <= 200; scale += 1) {
        demo.setOverallScale(scale);
        for (const value of [
            demo.minimumCardWidthIn,
            demo.maximumCardWidthIn,
            demo.minimumCardHeightIn,
            demo.maximumCardHeightIn,
        ]) {
            assert.equal(value, Number(value.toFixed(2)));
        }

        demo.setCardWidth(demo.maximumCardWidthIn);
        demo.setCardHeight(demo.maximumCardHeightIn);
        assert.ok(demo.printedCardWidthIn <= 8.5);
        assert.ok(demo.printedCardHeightIn <= 11);
    }
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
