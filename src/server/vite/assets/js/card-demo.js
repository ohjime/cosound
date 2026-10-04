function clamp(value, minimum = 0, maximum = 100) {
    return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function roundTo(value, places = 4) {
    const precision = 10 ** places;
    return Math.round((value + Number.EPSILON) * precision) / precision;
}

function floorTo(value, places) {
    const precision = 10 ** places;
    return Math.floor((value + Number.EPSILON) * precision) / precision;
}

function normalizeLayer(layer) {
    return {
        ...layer,
        gain: clamp(layer.gain ?? 50),
        mute: Boolean(layer.mute),
        isolated: Boolean(layer.isolated),
        saved: Boolean(layer.saved),
    };
}

function colorNameForHue(value) {
    const hue = clamp(value, 0, 360);
    if (hue < 15 || hue >= 345) return "Red";
    if (hue < 48) return "Warm umber";
    if (hue < 75) return "Gold";
    if (hue < 165) return "Green";
    if (hue < 195) return "Teal";
    if (hue < 250) return "Slate blue";
    if (hue < 290) return "Violet";
    if (hue < 330) return "Purple";
    return "Pink";
}

const LETTER_WIDTH_IN = 8.5;
const LETTER_HEIGHT_IN = 11;
const MAX_SHEET_CARDS = 12;
const MIN_CARD_WIDTH_IN = 1.5;
const MIN_CARD_HEIGHT_IN = 2.5;
const MIN_CARD_CONTENT_ALLOWANCE_IN = 1.125;
const MAX_CARD_WIDTH_IN = LETTER_WIDTH_IN;
const MAX_CARD_HEIGHT_IN = LETTER_HEIGHT_IN;
const MIN_GUIDE_IN = 0.25;
const MAX_GUIDE_IN = LETTER_HEIGHT_IN;
// The card's own corner, 1.125rem, in inches before scale.
const CARD_RADIUS_IN = 0.1875;
// Everything on a top-sheet card that belongs to the bottom sheet instead,
// besides the artwork's frame ring: boxes cut along their ringed outline,
// arrows along their stroked glyph.
const TOP_CUTOUT_BOXES = [
    "[data-card-demo-header]",
    "[data-card-demo-slider-control]",
    "[data-card-demo-volume-track]",
    "[data-card-demo-master-shell]",
].join(", ");
const TOP_CUTOUT_ARROWS = "[data-card-demo-side-arrow] svg, [data-card-demo-bottom-arrow] svg";

function svgNumber(value) {
    return String(roundTo(value, 4));
}

function roundedRectPath({ x, y, width, height }, [topLeft, topRight, bottomRight, bottomLeft]) {
    const n = svgNumber;
    return `M${n(x + topLeft)} ${n(y)}`
        + `H${n(x + width - topRight)}A${n(topRight)} ${n(topRight)} 0 0 1 ${n(x + width)} ${n(y + topRight)}`
        + `V${n(y + height - bottomRight)}A${n(bottomRight)} ${n(bottomRight)} 0 0 1 ${n(x + width - bottomRight)} ${n(y + height)}`
        + `H${n(x + bottomLeft)}A${n(bottomLeft)} ${n(bottomLeft)} 0 0 1 ${n(x)} ${n(y + height - bottomLeft)}`
        + `V${n(y + topLeft)}A${n(topLeft)} ${n(topLeft)} 0 0 1 ${n(x + topLeft)} ${n(y)}Z`;
}

function svgMaskUrl(width, height, body) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgNumber(width)} ${svgNumber(height)}" preserveAspectRatio="none">${body}</svg>`;
    return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

// Tailwind rings are zero-offset, zero-blur box shadows; the widest one is
// how far the ring paints outside the element.
function ringSpread(style) {
    let flat = style.boxShadow || "";
    while (/\([^()]*\)/.test(flat)) flat = flat.replace(/\([^()]*\)/g, "");
    let spread = 0;
    for (const shadow of flat.split(",")) {
        if (/\binset\b/.test(shadow)) continue;
        const [x, y, blur, size] = (shadow.match(/-?[\d.]+px/g) || []).map(parseFloat);
        if (x === 0 && y === 0 && blur === 0 && size > 0) spread = Math.max(spread, size);
    }
    return spread;
}

function cornerRadii(style, box, spread = 0) {
    const limit = Math.min(box.width, box.height) / 2;
    return [
        style.borderTopLeftRadius,
        style.borderTopRightRadius,
        style.borderBottomRightRadius,
        style.borderBottomLeftRadius,
    ].map((value = "0") => {
        const radius = String(value).endsWith("%")
            ? parseFloat(value) / 100 * Math.min(box.width, box.height)
            : parseFloat(value) || 0;
        return radius > 0 ? Math.min(radius, limit) + spread : 0;
    });
}

function grow(box, spread) {
    return {
        x: box.x - spread,
        y: box.y - spread,
        width: box.width + spread * 2,
        height: box.height + spread * 2,
    };
}

// Traces the pieces of one top-sheet card that belong to the bottom sheet as
// holes in a mask the size of the card: the artwork's frame ring, the layer
// indicator, the arrows, the mixer row and the bottom mixer tab. Each hole is
// the piece's full shape, ring included, so it notches into the artwork or
// flavor box wherever the piece overlaps them on screen.
function topCutoutMask(card) {
    const styleOf = (element) => globalThis.getComputedStyle(element);
    const bounds = card.getBoundingClientRect();
    const scale = bounds.width / card.offsetWidth || 1;
    const local = (element) => {
        const rect = element.getBoundingClientRect();
        return {
            x: (rect.left - bounds.left) / scale,
            y: (rect.top - bounds.top) / scale,
            width: rect.width / scale,
            height: rect.height / scale,
        };
    };
    const shown = (element) => element?.getClientRects().length > 0;
    const shapes = [];
    const frame = card.querySelector("[data-card-demo-artwork-frame]");
    if (shown(frame)) {
        const style = styleOf(frame);
        const box = local(frame);
        const spread = ringSpread(style);
        shapes.push(`<path fill="black" d="${roundedRectPath(grow(box, spread), cornerRadii(style, box, spread))}"/>`);
        shapes.push(`<path fill="white" d="${roundedRectPath(box, cornerRadii(style, box))}"/>`);
    }
    for (const piece of card.querySelectorAll(TOP_CUTOUT_BOXES)) {
        if (!shown(piece)) continue;
        const style = styleOf(piece);
        const box = local(piece);
        const spread = ringSpread(style);
        shapes.push(`<path fill="black" d="${roundedRectPath(grow(box, spread), cornerRadii(style, box, spread))}"/>`);
    }
    for (const icon of card.querySelectorAll(TOP_CUTOUT_ARROWS)) {
        const path = icon.querySelector("path");
        if (!shown(icon) || !path) continue;
        // The glyph box is already stretched by the arrow's own transform, so
        // mapping the viewBox onto it unevenly reproduces the drawn arrow.
        const box = local(icon);
        const viewBox = (icon.getAttribute("viewBox") || "0 0 24 24").split(/[\s,]+/).map(Number);
        const turn = parseFloat(styleOf(icon).rotate) || 0;
        const centerX = viewBox[0] + viewBox[2] / 2;
        const centerY = viewBox[1] + viewBox[3] / 2;
        shapes.push(
            `<svg x="${svgNumber(box.x)}" y="${svgNumber(box.y)}" width="${svgNumber(box.width)}" height="${svgNumber(box.height)}" viewBox="${viewBox.join(" ")}" preserveAspectRatio="none" overflow="visible">`
            + `<path transform="rotate(${turn} ${centerX} ${centerY})" fill="black" stroke="black" stroke-width="${path.getAttribute("stroke-width") || 0}" stroke-linejoin="round" d="${path.getAttribute("d")}"/>`
            + "</svg>",
        );
    }
    const width = card.offsetWidth;
    const height = card.offsetHeight;
    return svgMaskUrl(width, height,
        `<mask id="cutouts" maskUnits="userSpaceOnUse" x="0" y="0" width="${width}" height="${height}">`
        + `<rect width="${width}" height="${height}" fill="white"/>${shapes.join("")}</mask>`
        + `<rect width="${width}" height="${height}" mask="url(#cutouts)"/>`);
}

/** UI-only facsimile of the Explore card. It never creates or loads audio. */
export function cardDemo(initialLayers = []) {
    return {
        layers: initialLayers.map(normalizeLayer),
        currentIndex: 0,
        paused: false,
        mixSaved: false,
        cardHue: 128,
        cardBrightness: 18.4,
        ringHue: 128,
        ringBrightness: 20,
        cardWidthIn: 2,
        cardHeightIn: 3.5,
        overallScale: 100,
        cardGapIn: 0.25,
        splitLayers: false,
        topCutoutMask: "",
        showGuide: true,
        guideWidthIn: 2,
        guideHeightIn: 3.5,
        flavorText: "",
        flavorTextSize: 12,
        flavorOverlayUrl: "",
        flavorOverlayName: "",
        flavorOverlayError: "",
        flavorOverlayTintHue: 128,
        flavorOverlayTintBrightness: 50,
        flavorOverlayTintStrength: 0,
        indicatorText: "",
        indicatorTextSize: 14,
        indicatorTextSpacing: 0,
        indicatorCentered: false,
        masterText: "COSOUND",
        masterTextSize: 12,
        masterTextSpacing: 2.2,
        showLeftArrow: true,
        showRightArrow: true,
        showBottomArrow: true,
        bottomArrowValue: 50,
        uploadedArtworkUrl: "",
        uploadedArtworkName: "",
        artworkError: "",
        showArtworkText: false,
        artworkTitle: "",
        artistName: "",
        artworkTextSize: 18,
        showLikeButton: false,

        init() {
            // Web fonts change the layer indicator's width once they land.
            globalThis.document?.fonts?.ready.then(() => this.measureTopCutouts());
            const payload = this.$el?.querySelector("[data-card-demo-sounds] script");
            if (!payload) return;
            try {
                const layers = JSON.parse(payload.textContent);
                this.layers = Array.isArray(layers) ? layers.map(normalizeLayer) : [];
            } catch {
                this.layers = [];
            }
        },

        get currentLayer() {
            return this.layers[this.currentIndex] ?? null;
        },
        get isFirst() {
            return this.currentIndex === 0;
        },
        get isLast() {
            return this.currentIndex >= this.layers.length - 1;
        },
        get cardColorName() {
            return colorNameForHue(this.cardHue);
        },
        get ringColorName() {
            return colorNameForHue(this.ringHue);
        },
        get flavorOverlayTintName() {
            return colorNameForHue(this.flavorOverlayTintHue);
        },
        get colorName() {
            return this.cardColorName;
        },
        get scaleRatio() {
            return clamp(this.overallScale, 50, 200) / 100;
        },
        // Width and height are the card's own layout size. Scale magnifies the
        // finished card as a whole — artwork, arrows, text and padding alike —
        // so only the printed footprint grows; the sliders never move.
        get minimumCardWidthIn() {
            return Math.min(MIN_CARD_WIDTH_IN, this.maximumCardWidthIn);
        },
        get maximumCardWidthIn() {
            return floorTo(Math.min(MAX_CARD_WIDTH_IN, LETTER_WIDTH_IN / this.scaleRatio), 2);
        },
        get minimumCardHeightIn() {
            return roundTo(Math.min(
                this.maximumCardHeightIn,
                Math.max(
                    MIN_CARD_HEIGHT_IN,
                    this.effectiveCardWidthIn + MIN_CARD_CONTENT_ALLOWANCE_IN,
                ),
            ), 2);
        },
        get maximumCardHeightIn() {
            return floorTo(Math.min(MAX_CARD_HEIGHT_IN, LETTER_HEIGHT_IN / this.scaleRatio), 2);
        },
        get effectiveCardWidthIn() {
            return roundTo(clamp(
                this.cardWidthIn,
                this.minimumCardWidthIn,
                this.maximumCardWidthIn,
            ), 2);
        },
        get effectiveCardHeightIn() {
            return roundTo(clamp(
                this.cardHeightIn,
                this.minimumCardHeightIn,
                this.maximumCardHeightIn,
            ), 2);
        },
        get printedCardWidthIn() {
            return roundTo(Math.min(LETTER_WIDTH_IN, this.effectiveCardWidthIn * this.scaleRatio), 3);
        },
        get printedCardHeightIn() {
            return roundTo(Math.min(LETTER_HEIGHT_IN, this.effectiveCardHeightIn * this.scaleRatio), 3);
        },
        get islandPaddingXIn() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return roundTo(Math.min(
                gap,
                Math.max(0, (LETTER_WIDTH_IN - this.printedCardWidthIn) / 2),
            ));
        },
        get islandPaddingYIn() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return roundTo(Math.min(
                gap,
                Math.max(0, (LETTER_HEIGHT_IN - this.printedCardHeightIn) / 2),
            ));
        },
        get sheetColumns() {
            const availableWidth = LETTER_WIDTH_IN - this.islandPaddingXIn * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return Math.max(1, Math.floor((availableWidth + gap) / (this.printedCardWidthIn + gap)));
        },
        get sheetCapacityRows() {
            const availableHeight = LETTER_HEIGHT_IN - this.islandPaddingYIn * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return Math.max(1, Math.floor((availableHeight + gap) / (this.printedCardHeightIn + gap)));
        },
        get sheetCount() {
            const capacity = this.sheetColumns * this.sheetCapacityRows;
            if (capacity <= MAX_SHEET_CARDS) return capacity;
            return Math.max(this.sheetColumns, Math.floor(MAX_SHEET_CARDS / this.sheetColumns) * this.sheetColumns);
        },
        get sheetRows() {
            return Math.ceil(this.sheetCount / this.sheetColumns);
        },
        // The guide is measured in paper inches and centered on the middle
        // card of the top row (left of center when the column count is even).
        // Its size ignores scale and card size; only its center follows that
        // card as the centered grid island relays out.
        get guideColumn() {
            return Math.floor((this.sheetColumns - 1) / 2);
        },
        get islandWidthIn() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return this.sheetColumns * this.printedCardWidthIn
                + (this.sheetColumns - 1) * gap
                + this.islandPaddingXIn * 2;
        },
        get islandHeightIn() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return this.sheetRows * this.printedCardHeightIn
                + (this.sheetRows - 1) * gap
                + this.islandPaddingYIn * 2;
        },
        get guideCenterXIn() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return roundTo((LETTER_WIDTH_IN - this.islandWidthIn) / 2
                + this.islandPaddingXIn
                + this.guideColumn * (this.printedCardWidthIn + gap)
                + this.printedCardWidthIn / 2);
        },
        get guideCenterYIn() {
            return roundTo((LETTER_HEIGHT_IN - this.islandHeightIn) / 2 + this.islandPaddingYIn + this.printedCardHeightIn / 2);
        },
        get sheetCopies() {
            return Array.from({ length: this.sheetCount }, (_, index) => index + 1);
        },
        // Split printing lays the same sheet out twice. The top sheet is just
        // the card bodies — card color, artwork with its text, and the whole
        // flavor box — with transparent holes where everything else goes.
        // The bottom sheet is the border color around and between the cards
        // plus that everything else, with the card bodies left transparent.
        get printSheets() {
            if (!this.splitLayers) return [{ layer: "full", caption: "Letter sheet preview" }];
            return [
                { layer: "top", caption: "Sheet 1 · Top layer · cut out the holes" },
                { layer: "bottom", caption: "Sheet 2 · Bottom layer" },
            ];
        },
        // The bottom sheet's border color: the whole island minus each card's
        // rounded body, in paper inches.
        get bottomSheetMask() {
            const gap = clamp(this.cardGapIn, 0, 1.25);
            const width = this.printedCardWidthIn;
            const height = this.printedCardHeightIn;
            const radius = Math.min(CARD_RADIUS_IN * this.scaleRatio, width / 2, height / 2);
            const bodies = this.sheetCopies.map((copy) => roundedRectPath({
                x: this.islandPaddingXIn + ((copy - 1) % this.sheetColumns) * (width + gap),
                y: this.islandPaddingYIn + Math.floor((copy - 1) / this.sheetColumns) * (height + gap),
                width,
                height,
            }, [radius, radius, radius, radius]));
            const island = `M0 0H${svgNumber(this.islandWidthIn)}V${svgNumber(this.islandHeightIn)}H0Z`;
            return svgMaskUrl(this.islandWidthIn, this.islandHeightIn,
                `<path fill-rule="evenodd" d="${island}${bodies.join("")}"/>`);
        },
        // Everything that moves or resizes a top-sheet cut-out. Reading it in
        // an effect re-traces the holes whenever one of these changes.
        get topCutoutLayout() {
            return [
                this.splitLayers,
                this.effectiveCardWidthIn,
                this.effectiveCardHeightIn,
                this.indicatorText,
                this.indicatorTextSize,
                this.indicatorTextSpacing,
                this.indicatorCentered,
                this.showLeftArrow,
                this.showRightArrow,
                this.showBottomArrow,
                this.bottomArrowValue,
            ].join("|");
        },
        get printLayerStyle() {
            if (!this.splitLayers) return "";
            return [
                `--bottom-sheet-mask: ${this.bottomSheetMask}`,
                `--top-cutout-mask: ${this.topCutoutMask || "none"}`,
            ].join("; ");
        },
        // Every card shares one layout, so tracing the first top-sheet card
        // gives the holes for all of them.
        measureTopCutouts(root = globalThis.document) {
            const card = root?.querySelector('[data-print-layer="top"] [data-core-card]');
            if (card) this.topCutoutMask = topCutoutMask(card);
        },
        get editorStyle() {
            return [
                `--card-hue: ${clamp(this.cardHue, 0, 360)}`,
                `--card-brightness: ${clamp(this.cardBrightness)}%`,
                `--ring-hue: ${clamp(this.ringHue, 0, 360)}`,
                `--ring-brightness: ${clamp(this.ringBrightness)}%`,
                `--effective-card-width: ${this.effectiveCardWidthIn}in`,
                `--effective-card-height: ${this.effectiveCardHeightIn}in`,
                `--printed-card-width: ${this.printedCardWidthIn}in`,
                `--printed-card-height: ${this.printedCardHeightIn}in`,
                `--card-scale: ${this.scaleRatio}`,
                `--island-padding-x: ${this.islandPaddingXIn}in`,
                `--island-padding-y: ${this.islandPaddingYIn}in`,
                `--card-gap: ${clamp(this.cardGapIn, 0, 1.25)}in`,
                `--sheet-columns: ${this.sheetColumns}`,
                `--guide-width: ${this.guideWidthIn}in`,
                `--guide-height: ${this.guideHeightIn}in`,
                `--guide-center-x: ${this.guideCenterXIn}in`,
                `--guide-center-y: ${this.guideCenterYIn}in`,
            ].join("; ");
        },
        get flavorOverlayTintStyle() {
            if (!this.flavorOverlayUrl) return "";
            const imageMask = `url(\"${this.flavorOverlayUrl}\")`;
            return [
                `background-color: hsl(${clamp(this.flavorOverlayTintHue, 0, 360)} 75% ${clamp(this.flavorOverlayTintBrightness)}%)`,
                `opacity: ${clamp(this.flavorOverlayTintStrength) / 100}`,
                `mask-image: ${imageMask}`,
                "mask-mode: alpha",
                "mask-position: center",
                "mask-repeat: no-repeat",
                "mask-size: contain",
                `-webkit-mask-image: ${imageMask}`,
                "-webkit-mask-position: center",
                "-webkit-mask-repeat: no-repeat",
                "-webkit-mask-size: contain",
            ].join("; ");
        },

        setCardHue(value) {
            this.cardHue = clamp(value, 0, 360);
        },
        setCardBrightness(value) {
            this.cardBrightness = clamp(value);
        },
        setRingHue(value) {
            this.ringHue = clamp(value, 0, 360);
        },
        setRingBrightness(value) {
            this.ringBrightness = clamp(value);
        },
        setCardWidth(value) {
            this.cardWidthIn = roundTo(clamp(value, this.minimumCardWidthIn, this.maximumCardWidthIn), 2);
        },
        setCardHeight(value) {
            this.cardHeightIn = roundTo(clamp(value, this.minimumCardHeightIn, this.maximumCardHeightIn), 2);
        },
        setOverallScale(value) {
            this.overallScale = clamp(value, 50, 200);
        },
        setCardGap(value) {
            this.cardGapIn = clamp(value, 0, 1.25);
        },
        setGuideWidth(value) {
            this.guideWidthIn = roundTo(clamp(value, MIN_GUIDE_IN, MAX_GUIDE_IN), 2);
        },
        setGuideHeight(value) {
            this.guideHeightIn = roundTo(clamp(value, MIN_GUIDE_IN, MAX_GUIDE_IN), 2);
        },
        setFlavorTextSize(value) {
            this.flavorTextSize = clamp(value, 8, 28);
        },
        setFlavorOverlayTintHue(value) {
            this.flavorOverlayTintHue = clamp(value, 0, 360);
        },
        setFlavorOverlayTintBrightness(value) {
            this.flavorOverlayTintBrightness = clamp(value);
        },
        setFlavorOverlayTintStrength(value) {
            this.flavorOverlayTintStrength = clamp(value);
        },
        loadFlavorOverlay(event) {
            const file = event?.target?.files?.[0];
            if (!file) return false;
            const loaded = this.setFlavorOverlay(file);
            if (event?.target) event.target.value = "";
            return loaded;
        },
        setFlavorOverlay(file) {
            if (!file.type?.startsWith("image/")) {
                this.flavorOverlayError = "Choose an image file.";
                return false;
            }
            if (file.size > 10 * 1024 * 1024) {
                this.flavorOverlayError = "Choose an image smaller than 10 MB.";
                return false;
            }
            const nextUrl = URL.createObjectURL(file);
            if (this.flavorOverlayUrl.startsWith("blob:")) {
                URL.revokeObjectURL(this.flavorOverlayUrl);
            }
            this.flavorOverlayUrl = nextUrl;
            this.flavorOverlayName = file.name;
            this.flavorOverlayError = "";
            return true;
        },
        clearFlavorOverlay() {
            if (this.flavorOverlayUrl.startsWith("blob:")) {
                URL.revokeObjectURL(this.flavorOverlayUrl);
            }
            this.flavorOverlayUrl = "";
            this.flavorOverlayName = "";
            this.flavorOverlayError = "";
        },
        setIndicatorTextSize(value) {
            this.indicatorTextSize = clamp(value, 8, 24);
        },
        setIndicatorTextSpacing(value) {
            this.indicatorTextSpacing = clamp(value, -1, 8);
        },
        setMasterTextSize(value) {
            this.masterTextSize = clamp(value, 8, 24);
        },
        setMasterTextSpacing(value) {
            this.masterTextSpacing = clamp(value, -1, 8);
        },
        setBottomArrowValue(value) {
            this.bottomArrowValue = clamp(value);
        },
        setArtworkTextSize(value) {
            this.artworkTextSize = clamp(value, 8, 32);
        },
        loadArtwork(event) {
            const file = event?.target?.files?.[0];
            if (!file) return false;
            const loaded = this.setArtwork(file);
            if (event?.target) event.target.value = "";
            return loaded;
        },
        setArtwork(file) {
            if (!file.type?.startsWith("image/")) {
                this.artworkError = "Choose an image file.";
                return false;
            }
            if (file.size > 10 * 1024 * 1024) {
                this.artworkError = "Choose an image smaller than 10 MB.";
                return false;
            }
            const nextUrl = URL.createObjectURL(file);
            if (this.uploadedArtworkUrl.startsWith("blob:")) {
                URL.revokeObjectURL(this.uploadedArtworkUrl);
            }
            this.uploadedArtworkUrl = nextUrl;
            this.uploadedArtworkName = file.name;
            this.artworkError = "";
            return true;
        },
        clearArtwork() {
            if (this.uploadedArtworkUrl.startsWith("blob:")) {
                URL.revokeObjectURL(this.uploadedArtworkUrl);
            }
            this.uploadedArtworkUrl = "";
            this.uploadedArtworkName = "";
            this.artworkError = "";
        },
        destroy() {
            this.clearArtwork();
            this.clearFlavorOverlay();
        },

        anyIsolated() {
            return this.layers.some((layer) => layer.isolated);
        },
        isSilenced(layer) {
            if (!layer) return false;
            return layer.mute || (this.anyIsolated() && !layer.isolated);
        },
        grayscaleFor(layer) {
            if (!layer) return 0;
            if (this.isSilenced(layer)) return 100;
            return clamp(100 - layer.gain);
        },

        select(index) {
            if (this.layers.length === 0) return;
            this.currentIndex = clamp(index, 0, this.layers.length - 1);
            this.$el?.querySelectorAll("[data-card-demo-carousel]").forEach((carousel) => {
                const item = carousel.querySelectorAll("[data-card-demo-layer]")[this.currentIndex];
                if (item) carousel.scrollTo({ left: item.offsetLeft, behavior: "instant" });
            });
        },
        move(delta) {
            this.select(this.currentIndex + delta);
        },
        updateActive(carousel) {
            if (!carousel) return;
            const items = carousel.querySelectorAll("[data-card-demo-layer]");
            let distance = Infinity;
            for (let index = 0; index < items.length; index += 1) {
                const candidate = Math.abs(items[index].offsetLeft - carousel.scrollLeft);
                if (candidate < distance) {
                    distance = candidate;
                    this.currentIndex = index;
                }
            }
        },

        toggleFavorite(layer) {
            if (layer) layer.saved = !layer.saved;
        },
        toggleMute(layer) {
            if (!layer) return;
            const wasMuted = layer.mute;
            layer.mute = !layer.mute;
            if (wasMuted && !layer.isolated && this.anyIsolated()) {
                this.layers.forEach((candidate) => { candidate.isolated = false; });
            }
            this.mixSaved = false;
        },
        toggleIsolate(layer) {
            if (!layer) return;
            if (layer.isolated) {
                layer.isolated = false;
                this.mixSaved = false;
                return;
            }
            this.layers.forEach((candidate) => {
                if (candidate !== layer && candidate.isolated) {
                    candidate.isolated = false;
                    candidate.mute = true;
                }
            });
            layer.mute = false;
            layer.isolated = true;
            this.mixSaved = false;
        },
        setCurrentGain(value) {
            if (!this.currentLayer) return;
            this.currentLayer.gain = clamp(value);
            this.currentLayer.mute = false;
            if (!this.currentLayer.isolated && this.anyIsolated()) {
                this.layers.forEach((layer) => { layer.isolated = false; });
            }
            this.mixSaved = false;
        },
        setGainFromPointer(event, track) {
            const bounds = track?.getBoundingClientRect();
            if (!bounds?.width) return;
            this.setCurrentGain(((event.clientX - bounds.left) / bounds.width) * 100);
        },
        stepGain(delta) {
            this.setCurrentGain((this.currentLayer?.gain ?? 0) + delta);
        },
        adjustAll(delta) {
            this.layers.forEach((layer) => { layer.gain = clamp(layer.gain + delta); });
            this.mixSaved = false;
        },
    };
}
