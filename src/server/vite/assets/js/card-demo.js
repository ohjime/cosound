function clamp(value, minimum = 0, maximum = 100) {
    return Math.max(minimum, Math.min(maximum, Number(value) || 0));
}

function roundTo(value, places = 4) {
    const precision = 10 ** places;
    return Math.round((value + Number.EPSILON) * precision) / precision;
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

const LETTER_WIDTH_MM = 215.9;
const LETTER_HEIGHT_MM = 279.4;
const SHEET_PADDING_MM = 6.35;
const MAX_SHEET_CARDS = 12;
const MIN_CARD_WIDTH_MM = 35;
const MAX_CARD_WIDTH_MM = 100;
const MIN_CARD_HEIGHT_MM = 73.1;
const MAX_CARD_HEIGHT_MM = 150;
const MIN_CARD_BODY_MM = 38.1;

/** UI-only facsimile of the Explore card. It never creates or loads audio. */
export function cardDemo(initialLayers = []) {
    return {
        layers: initialLayers.map(normalizeLayer),
        currentIndex: 0,
        paused: false,
        mixSaved: false,
        cardHue: 128,
        ringHue: 128,
        cardWidthMm: 50.8,
        cardHeightMm: 88.9,
        overallScale: 100,
        cardGapIn: 0.25,
        indicatorText: "",
        indicatorTextSize: 14,
        indicatorCentered: false,
        masterText: "COSOUND",
        showLeftArrow: true,
        showRightArrow: true,
        showBottomArrow: true,
        bottomArrowValue: 50,
        uploadedArtworkUrl: "",
        uploadedArtworkName: "",
        artworkError: "",
        showArtworkText: true,
        artworkTitle: "",
        artistName: "",
        artworkTextSize: 18,
        showLikeButton: false,

        init() {
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
        get colorName() {
            return this.cardColorName;
        },
        get scaleRatio() {
            return clamp(this.overallScale, 80, 200) / 100;
        },
        get effectiveCardWidthMm() {
            return roundTo(clamp(this.cardWidthMm, MIN_CARD_WIDTH_MM, MAX_CARD_WIDTH_MM) * this.scaleRatio);
        },
        get effectiveCardHeightMm() {
            return roundTo(clamp(this.cardHeightMm, MIN_CARD_HEIGHT_MM, MAX_CARD_HEIGHT_MM) * this.scaleRatio);
        },
        get sheetColumns() {
            const availableWidth = LETTER_WIDTH_MM - SHEET_PADDING_MM * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25) * 25.4;
            const columns = Math.floor((availableWidth + gap) / (this.effectiveCardWidthMm + gap));
            return Math.min(MAX_SHEET_CARDS, Math.max(1, columns));
        },
        get sheetCapacityRows() {
            const availableHeight = LETTER_HEIGHT_MM - SHEET_PADDING_MM * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25) * 25.4;
            return Math.max(0, Math.floor((availableHeight + gap) / (this.effectiveCardHeightMm + gap)));
        },
        get sheetCount() {
            const capacity = this.sheetColumns * this.sheetCapacityRows;
            if (capacity <= MAX_SHEET_CARDS) return capacity;
            return Math.max(this.sheetColumns, Math.floor(MAX_SHEET_CARDS / this.sheetColumns) * this.sheetColumns);
        },
        get sheetRows() {
            return Math.ceil(this.sheetCount / this.sheetColumns);
        },
        get sheetCopies() {
            return Array.from({ length: this.sheetCount }, (_, index) => index + 1);
        },
        get editorStyle() {
            return [
                `--card-hue: ${clamp(this.cardHue, 0, 360)}`,
                `--ring-hue: ${clamp(this.ringHue, 0, 360)}`,
                `--card-width: ${clamp(this.cardWidthMm, MIN_CARD_WIDTH_MM, MAX_CARD_WIDTH_MM)}mm`,
                `--card-height: ${clamp(this.cardHeightMm, MIN_CARD_HEIGHT_MM, MAX_CARD_HEIGHT_MM)}mm`,
                `--effective-card-width: ${this.effectiveCardWidthMm}mm`,
                `--effective-card-height: ${this.effectiveCardHeightMm}mm`,
                `--card-scale: ${this.scaleRatio}`,
                `--card-gap: ${clamp(this.cardGapIn, 0, 1.25)}in`,
                `--sheet-columns: ${this.sheetColumns}`,
            ].join("; ");
        },

        setCardHue(value) {
            this.cardHue = clamp(value, 0, 360);
        },
        setRingHue(value) {
            this.ringHue = clamp(value, 0, 360);
        },
        setCardWidth(value) {
            this.cardWidthMm = roundTo(clamp(value, MIN_CARD_WIDTH_MM, MAX_CARD_WIDTH_MM), 1);
            const minimumHeight = this.cardWidthMm + MIN_CARD_BODY_MM;
            if (this.cardHeightMm < minimumHeight) {
                this.cardHeightMm = roundTo(clamp(minimumHeight, MIN_CARD_HEIGHT_MM, MAX_CARD_HEIGHT_MM), 1);
            }
        },
        setCardHeight(value) {
            this.cardHeightMm = roundTo(clamp(value, MIN_CARD_HEIGHT_MM, MAX_CARD_HEIGHT_MM), 1);
            const maximumWidth = this.cardHeightMm - MIN_CARD_BODY_MM;
            if (this.cardWidthMm > maximumWidth) {
                this.cardWidthMm = roundTo(clamp(maximumWidth, MIN_CARD_WIDTH_MM, MAX_CARD_WIDTH_MM), 1);
            }
        },
        setOverallScale(value) {
            this.overallScale = clamp(value, 80, 200);
        },
        setCardGap(value) {
            this.cardGapIn = clamp(value, 0, 1.25);
        },
        setIndicatorTextSize(value) {
            this.indicatorTextSize = clamp(value, 8, 24);
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
