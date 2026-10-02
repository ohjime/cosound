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

const LETTER_WIDTH_IN = 8.5;
const LETTER_HEIGHT_IN = 11;
const SHEET_PADDING_IN = 0.25;
const MAX_SHEET_CARDS = 12;
const MIN_CARD_WIDTH_IN = 1.5;
const MIN_CARD_HEIGHT_IN = 2.5;
const MIN_CARD_CONTENT_ALLOWANCE_IN = 1.125;
const MAX_CARD_WIDTH_IN = LETTER_WIDTH_IN;
const MAX_CARD_HEIGHT_IN = LETTER_HEIGHT_IN;

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
            return clamp(this.overallScale, 80, 100) / 100;
        },
        get minimumCardWidthIn() {
            return roundTo(MIN_CARD_WIDTH_IN * this.scaleRatio, 2);
        },
        get maximumCardWidthIn() {
            return MAX_CARD_WIDTH_IN;
        },
        get minimumCardHeightIn() {
            return roundTo(Math.min(
                MAX_CARD_HEIGHT_IN,
                Math.max(
                    MIN_CARD_HEIGHT_IN * this.scaleRatio,
                    this.effectiveCardWidthIn + MIN_CARD_CONTENT_ALLOWANCE_IN,
                ),
            ), 2);
        },
        get maximumCardHeightIn() {
            return MAX_CARD_HEIGHT_IN;
        },
        get effectiveCardWidthIn() {
            return roundTo(clamp(
                this.cardWidthIn * this.scaleRatio,
                this.minimumCardWidthIn,
                MAX_CARD_WIDTH_IN,
            ), 2);
        },
        get effectiveCardHeightIn() {
            return roundTo(clamp(
                this.cardHeightIn * this.scaleRatio,
                this.minimumCardHeightIn,
                MAX_CARD_HEIGHT_IN,
            ), 2);
        },
        get sheetPaddingXIn() {
            return roundTo(Math.min(
                SHEET_PADDING_IN,
                Math.max(0, (LETTER_WIDTH_IN - this.effectiveCardWidthIn) / 2),
            ));
        },
        get sheetPaddingYIn() {
            return roundTo(Math.min(
                SHEET_PADDING_IN,
                Math.max(0, (LETTER_HEIGHT_IN - this.effectiveCardHeightIn) / 2),
            ));
        },
        get sheetColumns() {
            const availableWidth = LETTER_WIDTH_IN - this.sheetPaddingXIn * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return Math.max(1, Math.floor((availableWidth + gap) / (this.effectiveCardWidthIn + gap)));
        },
        get sheetCapacityRows() {
            const availableHeight = LETTER_HEIGHT_IN - this.sheetPaddingYIn * 2;
            const gap = clamp(this.cardGapIn, 0, 1.25);
            return Math.max(1, Math.floor((availableHeight + gap) / (this.effectiveCardHeightIn + gap)));
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
                `--card-brightness: ${clamp(this.cardBrightness)}%`,
                `--ring-hue: ${clamp(this.ringHue, 0, 360)}`,
                `--ring-brightness: ${clamp(this.ringBrightness)}%`,
                `--effective-card-width: ${this.effectiveCardWidthIn}in`,
                `--effective-card-height: ${this.effectiveCardHeightIn}in`,
                `--sheet-padding-x: ${this.sheetPaddingXIn}in`,
                `--sheet-padding-y: ${this.sheetPaddingYIn}in`,
                `--card-gap: ${clamp(this.cardGapIn, 0, 1.25)}in`,
                `--sheet-columns: ${this.sheetColumns}`,
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
            const physicalWidth = clamp(value, this.minimumCardWidthIn, this.maximumCardWidthIn);
            this.cardWidthIn = roundTo(physicalWidth / this.scaleRatio);
        },
        setCardHeight(value) {
            const physicalHeight = clamp(value, this.minimumCardHeightIn, this.maximumCardHeightIn);
            this.cardHeightIn = roundTo(physicalHeight / this.scaleRatio);
        },
        setOverallScale(value) {
            this.overallScale = clamp(value, 80, 100);
        },
        setCardGap(value) {
            this.cardGapIn = clamp(value, 0, 1.25);
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
