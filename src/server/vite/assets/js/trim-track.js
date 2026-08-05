import {
    DEFAULT_PEAK_BUCKETS,
    MIN_REGION_SECONDS,
    peaksFromBuffer,
} from "./soundscape-mixer.js";

/**
 * The trim track: a waveform of a file, a start and an end marker dragged over
 * it, and the playheads sweeping through it.
 *
 * Registered as the `trimTrack` Alpine component and used as a bare div — it
 * builds its own inside, because a canvas, two draggable markers, their labels
 * and a sweep are one widget, not markup a template should have to keep in step:
 *
 *   <div x-data="trimTrack()"
 *        x-effect="load({ src, duration, start, end, index, gainDb })"
 *        @trim-commit="retime($event.detail)"></div>
 *
 * `load` is the whole input and `trim-commit` the whole output. Driving it from
 * `x-effect` rather than from `x-data` arguments is what makes it follow the
 * layer being edited: the effect re-runs whenever anything it read changed —
 * switching tabs, the Reset button, or the engine writing a corrected crop back
 * — and the markers move to match. There is no second copy of the crop here to
 * fall out of step with the store.
 *
 * Commits carry `{ trim_start, trim_end }` in seconds and fire on release, not
 * during the drag, because the store's setTiming rebuilds the voice: a drag
 * should cost one rebuild, the same way the range inputs this replaced only
 * fired on `change`. An end marker parked at the tail commits `trim_end: null`,
 * which is what "to the end" is everywhere else in the pipeline — a number that
 * merely happens to equal today's duration would silently become a real crop if
 * the layer were ever given a longer file.
 *
 * ## Where the waveform comes from
 *
 * No library. The envelope is min/max over the decoded samples, which is what
 * `peaksFromBuffer` in the engine does, and the engine is also where the decoded
 * buffers already are: `cosoundMixer.peaksFor(url)` reads the buffer the layer
 * is playing out of the same cache the voice loaded it from, so drawing a layer
 * costs neither a fetch nor a decode. Only a src the engine has never seen falls
 * back to fetching and decoding here.
 *
 * ## The playheads
 *
 * `index` is the voice to ask, and the answer comes from the engine's schedule
 * rather than from a clock here — see `layerPlayheads`. There is more than one:
 * a voice runs two schedules of the same crop, and spacing them apart is exactly
 * what `stretch` does, so a layer has two heads, one, or none. Drawing only the
 * passes that are genuinely sounding is the honest picture and it is also the
 * legible one — what the Stretch slider does becomes something you can watch,
 * and the silence between passes reads as silence instead of as a stuck marker.
 *
 * ## Why none of this is Alpine state
 *
 * The crop, the peaks and the drag all live in this factory's closure rather
 * than on the returned object. Nothing in a template binds to them — the panel
 * renders itself onto a canvas and moves its own markers — so being reactive
 * would buy nothing and cost something real: `x-effect` tracks every reactive
 * property read while it runs, so a `load` that read them would re-subscribe to
 * its own writes and re-enter itself on every pointermove of a drag. Closure
 * variables are invisible to the tracker, which leaves the effect subscribed to
 * exactly what the template passed in.
 *
 * ## Why the panel is dark in both themes
 *
 * A waveform is drawn to a canvas, which knows nothing about daisyUI's tokens,
 * and the colours that read as an audio envelope — the amplitude gradient
 * below — need a dark ground under them to do it. Rather than theme the canvas,
 * this panel is a screen: it stays dark under `winter` and `dim` alike, the way
 * a meter or a scope does.
 */

// Bars are sized in CSS pixels, and the envelope is folded down to however many
// fit. The stored resolution is much higher than any panel is wide, so resizing
// redraws from the same peaks.
const BAR_WIDTH = 2;
const BAR_GAP = 1;

// Amplitude gradient, top of the panel to the bottom, mirrored about the axis:
// green at the extremes, through yellow and orange, to a bright line at zero.
// Quiet passages only ever paint near the axis, so they come out cool and the
// loud ones warm — the file's dynamics read off the panel without a scale.
const WAVE_STOPS = [
    [0, "#4ade80"],
    [0.18, "#a3e635"],
    [0.33, "#facc15"],
    [0.44, "#fb923c"],
    [0.48, "#f87171"],
    [0.5, "#a5f3fc"],
    [0.52, "#f87171"],
    [0.56, "#fb923c"],
    [0.67, "#facc15"],
    [0.82, "#a3e635"],
    [1, "#4ade80"],
];

const HANDLES = [
    { key: "start", label: "Start", edge: "top" },
    { key: "end", label: "End", edge: "bottom" },
];

// How many playheads the panel keeps elements for. A voice runs two schedules of
// the same crop — spacing them apart is what `stretch` does — and each of those
// can be sounding twice at once while a loop crossfade runs, one pass on its way
// out of the tail and one arriving at the head. So four is the ceiling, any
// number of them may be idle, and the engine reports whichever are genuinely
// sounding.
const MAX_PLAYHEADS = 4;

/** Arrow-key nudge; Shift and PageUp/PageDown are multiples of it, in seconds. */
const NUDGE_SECONDS = 0.05;

function clamp(value, low, high) {
    return Math.min(Math.max(Number(value) || 0, low), high);
}

/**
 * `M:SS.mmm`, the resolution a trim handle is actually placed at. The settings
 * pane's own `clock()` rounds to a tenth, which is right for reading a length
 * off a line of prose and too coarse for aiming at the head of a transient.
 */
export function clockText(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(total / 60);
    return `${minutes}:${(total - minutes * 60).toFixed(3).padStart(6, "0")}`;
}

// Only ever built for a src the engine does not hold — see above. One context
// for the page, left suspended: decodeAudioData does not need it running, and
// one per component would run the browser out of them.
let fallbackContext = null;

async function decodeStandalone(url) {
    const AudioContextClass = globalThis.AudioContext ?? globalThis.webkitAudioContext;
    if (!AudioContextClass) throw new Error("This browser has no Web Audio support.");
    fallbackContext ??= new AudioContextClass();
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Could not load ${url} (${response.status}).`);
    return fallbackContext.decodeAudioData(await response.arrayBuffer());
}

async function peaksForSource(src, buckets) {
    const engine = globalThis.cosoundMixer;
    if (typeof engine?.peaksFor === "function") return engine.peaksFor(src, buckets);
    return peaksFromBuffer(await decodeStandalone(src), buckets);
}

export function trimTrack({ buckets = DEFAULT_PEAK_BUCKETS } = {}) {
    // Everything the panel knows, kept out of Alpine's reactivity on purpose.
    let src = "";
    let duration = 0;
    let start = 0;
    let end = 0;
    let peaks = null;
    let note = "";
    // The layer's make-up gain in dB, which is what loudness matching actually
    // does to it — see `drawWave`. Zero is an unmatched layer.
    let gainDb = 0;
    // Which voice to ask for playheads. null when the caller did not say, which
    // is how the panel is used outside a running mix.
    let voiceIndex = null;
    let frame = null;
    // Which marker the pointer or the keyboard currently owns, if any. Also the
    // guard that stops `load` yanking a marker out from under a drag when the
    // store changes for some other reason mid-gesture.
    let dragging = null;
    let request = 0;
    let observer = null;
    let dom = null;
    let loaded = false;

    /** The shortest crop the engine will accept, capped by the file itself. */
    const minSpan = () => Math.min(MIN_REGION_SECONDS, duration);

    function timeAt(clientX) {
        const box = dom.screen.getBoundingClientRect();
        if (!box.width) return 0;
        return clamp((clientX - box.left) / box.width, 0, 1) * duration;
    }

    /** Move one marker, keeping the pair a playable region apart. */
    function moveTo(which, seconds) {
        const time = clamp(seconds, 0, duration);
        const gap = minSpan();
        if (which === "start") start = Math.min(time, Math.max(0, end - gap));
        else end = Math.max(time, Math.min(duration, start + gap));
        paint();
    }

    /**
     * Everything that moves with the markers: the two shades, the marker lines
     * and their labels. Cheap enough to run on every pointermove — the canvas is
     * untouched, because the waveform does not change when the crop does. What
     * is cut is shaded over the wave rather than drawn out of it, so the artist
     * can still see what they are giving up.
     */
    function paint() {
        if (!dom) return;
        const span = duration || 1;
        const head = clamp(start / span, 0, 1);
        const tail = clamp(end / span, 0, 1);
        dom.shadeHead.style.width = `${head * 100}%`;
        dom.shadeTail.style.width = `${(1 - tail) * 100}%`;
        place("start", head, start);
        place("end", tail, end);
        dom.total.textContent = clockText(duration);
        dom.note.textContent = note;
        dom.note.style.display = note ? "" : "none";
    }

    function place(which, fraction, seconds) {
        const handle = dom.handles[which];
        handle.style.left = `${fraction * 100}%`;
        dom.labels[which].textContent = clockText(seconds);
        handle.setAttribute("aria-valuenow", seconds.toFixed(3));
        handle.setAttribute("aria-valuetext", clockText(seconds));
        handle.setAttribute("aria-valuemax", duration.toFixed(3));
        // Keep the label inside the panel: near either edge it slides along the
        // marker rather than being clipped by the panel's overflow.
        const width = dom.screen.clientWidth;
        const pill = dom.labels[which].parentElement;
        const centre = fraction * width;
        const room = Math.max(2, width - pill.offsetWidth - 2);
        pill.style.transform = `translateX(${clamp(centre - pill.offsetWidth / 2, 2, room) - centre}px)`;
    }

    function drawWave() {
        if (!dom) return;
        const width = dom.screen.clientWidth;
        const height = dom.screen.clientHeight;
        if (!width || !height) return;
        // Capped at 2: past that the extra pixels cost real time on a phone and
        // buy nothing on a 2px bar.
        const ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
        dom.canvas.width = Math.round(width * ratio);
        dom.canvas.height = Math.round(height * ratio);
        const context = dom.canvas.getContext("2d");
        if (!context) return;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);
        paint();
        if (!peaks) return;

        const gradient = context.createLinearGradient(0, 0, 0, height);
        for (const [at, colour] of WAVE_STOPS) gradient.addColorStop(at, colour);
        context.fillStyle = gradient;

        const middle = height / 2;
        const bars = Math.max(1, Math.floor(width / (BAR_WIDTH + BAR_GAP)));
        const step = width / bars;
        const barWidth = Math.max(1, step - BAR_GAP);
        // Two things decide the vertical scale.
        //
        // The base is the file's own peak: a trim is aimed at the shape of a
        // recording — where it starts, where the tail dies away — and a quiet one
        // drawn true to full scale is a flat line with no shape to aim at. So an
        // unmatched layer fills the panel whatever it was recorded at.
        //
        // On top of that rides the loudness make-up gain, because that is not a
        // number about the file — it is a factor the engine puts on the voice's
        // gain node, so it really is the amplitude coming out. Dragging the
        // target grows or shrinks the wave against the same panel, which is the
        // comparison the control is for. What it is *not* is the fader: that
        // decides how this layer sits against the others, and belongs to the
        // fader on the card, not to a picture of one layer.
        const makeup = 10 ** (gainDb / 20);
        const scale = peaks.peak > 0.0001 ? ((middle - 1) / peaks.peak) * makeup : 0;
        const { min, max, length } = peaks;
        for (let bar = 0; bar < bars; bar += 1) {
            const from = Math.floor((bar * length) / bars);
            const to = Math.min(length, Math.max(from + 1, Math.floor(((bar + 1) * length) / bars)));
            let low = 0;
            let high = 0;
            for (let i = from; i < to; i += 1) {
                if (min[i] < low) low = min[i];
                if (max[i] > high) high = max[i];
            }
            // Clamped to the panel rather than scaled to fit, so a layer being
            // pushed hard reads as running out of room instead of quietly
            // renormalising and looking unchanged.
            const top = Math.max(0, middle - high * scale);
            const bottom = Math.min(height, middle - low * scale);
            // Silence still gets a hairline, so the run-in of a recording reads
            // as file rather than as a hole in the panel.
            context.fillRect(bar * step, top, barWidth, Math.max(1, bottom - top));
        }
    }

    /**
     * Sweep the playheads. Runs off the engine's schedule rather than a clock of
     * its own, so it is right across a pause and after a rebuild, and off rAF
     * rather than a timer, so it stops dead when the tab is hidden.
     */
    function followPlayheads() {
        frame = requestAnimationFrame(followPlayheads);
        if (!dom) return;
        const engine = globalThis.cosoundMixer;
        const heads = voiceIndex == null || typeof engine?.layerPlayheads !== "function"
            ? []
            : engine.layerPlayheads(voiceIndex);
        const width = dom.screen.clientWidth;
        for (const [slot, head] of dom.playheads.entries()) {
            const at = heads[slot];
            // Nothing sounding on this pass: the drift between passes is a gap,
            // not a loop, so the head goes away rather than parking somewhere.
            if (at == null || !duration || !width) {
                head.root.style.display = "none";
                continue;
            }
            head.root.style.display = "";
            const fraction = clamp(at / duration, 0, 1);
            head.root.style.left = `${fraction * 100}%`;
            const text = clockText(at);
            if (head.label.textContent !== text) {
                head.label.textContent = text;
                // Monospace and near enough fixed-width, so the measurement only
                // has to be redone when the string changes length — reading
                // offsetWidth every frame would force a layout 60 times a second.
                if (text.length !== head.measured) {
                    head.width = head.label.offsetWidth;
                    head.measured = text.length;
                }
            }
            const centre = fraction * width;
            const room = Math.max(2, width - head.width - 2);
            head.label.style.transform = `translateX(${clamp(centre - head.width / 2, 2, room) - centre}px)`;
        }
    }

    async function fetchPeaks() {
        const token = (request += 1);
        if (!src) return;
        try {
            const result = await peaksForSource(src, buckets);
            // A tab switched during the fetch already asked for something else;
            // that request owns the panel now.
            if (token !== request) return;
            peaks = result;
            note = "";
        } catch {
            if (token !== request) return;
            note = "Could not read this file's waveform.";
        }
        drawWave();
    }

    return {
        init() {
            dom = build(this.$el, {
                down: (event) => {
                    if (!duration || event.button > 0) return;
                    const grabbed = event.target.closest?.("[data-trim-handle]");
                    const time = timeAt(event.clientX);
                    dragging = grabbed?.dataset.trimHandle
                        ?? (Math.abs(time - start) <= Math.abs(time - end) ? "start" : "end");
                    // Pressing empty track sends the nearer marker there; pressing
                    // a marker picks it up where it already is, so it does not
                    // jump out from under the finger that grabbed it.
                    if (!grabbed) moveTo(dragging, time);
                    event.preventDefault();
                    dom.screen.setPointerCapture(event.pointerId);
                    dom.handles[dragging].focus({ preventScroll: true });
                },
                move: (event) => {
                    if (dragging) moveTo(dragging, timeAt(event.clientX));
                },
                up: () => {
                    if (!dragging) return;
                    dragging = null;
                    this.commit();
                },
                // Each marker is a slider in its own right, so the crop stays
                // reachable without a pointer — the two range inputs this panel
                // replaced were.
                key: (event, which) => {
                    const step = event.shiftKey ? NUDGE_SECONDS * 10 : NUDGE_SECONDS;
                    const from = which === "start" ? start : end;
                    let next = from;
                    switch (event.key) {
                        case "ArrowLeft":
                        case "ArrowDown": next = from - step; break;
                        case "ArrowRight":
                        case "ArrowUp": next = from + step; break;
                        case "PageDown": next = from - step * 10; break;
                        case "PageUp": next = from + step * 10; break;
                        case "Home": next = 0; break;
                        case "End": next = duration; break;
                        default: return;
                    }
                    event.preventDefault();
                    moveTo(which, next);
                    this.commit();
                },
            });
            // The panel lives inside an `x-show`, so it is very often zero-sized
            // when this runs. The observer is what draws it: the first non-zero
            // box arrives as a resize, exactly like every later one.
            observer = new ResizeObserver(() => drawWave());
            observer.observe(dom.screen);
            followPlayheads();
        },

        destroy() {
            observer?.disconnect();
            observer = null;
            if (frame != null) cancelAnimationFrame(frame);
            frame = null;
        },

        /**
         * Point the track at a file and a crop. Safe to call on every change —
         * it only refetches when the src is new.
         */
        load(next = {}) {
            const nextSrc = String(next.src || "");
            // The first call always counts as a change, so a layer that opens
            // with no sound gets told so rather than sitting on a blank panel.
            const changed = nextSrc !== src || !loaded;
            loaded = true;
            src = nextSrc;
            duration = Math.max(0, Number(next.duration) || 0);
            voiceIndex = Number.isInteger(next.index) ? next.index : null;
            // The make-up gain is a vertical scale, so a new one is a redraw and
            // nothing more — the loudness slider rides this on every `input`.
            const rescaled = (Number(next.gainDb) || 0) !== gainDb;
            gainDb = Number(next.gainDb) || 0;
            if (!dragging) {
                start = clamp(next.start, 0, duration);
                end = next.end == null ? duration : clamp(next.end, start, duration);
            }
            if (!changed) {
                if (rescaled) drawWave();
                else paint();
                return;
            }
            peaks = null;
            note = src ? "Reading waveform…" : "No sound on this layer yet.";
            drawWave();
            fetchPeaks();
        },

        commit() {
            // `null`, not the duration: "to the end" has to survive the layer
            // later being given a longer file.
            const wholeTail = end >= duration - 0.001;
            this.$dispatch("trim-commit", {
                trim_start: Number(start.toFixed(3)),
                trim_end: wholeTail ? null : Number(end.toFixed(3)),
            });
        },
    };
}

/**
 * Build the panel inside the host div and hand back the parts that get moved.
 * Tailwind sees these class strings — main.css sources this directory — so they
 * are ordinary utilities and not a second styling system.
 */
function build(root, on) {
    root.classList.add("flex", "w-full", "flex-col", "gap-1", "select-none");

    const screen = document.createElement("div");
    screen.className = "relative h-32 w-full touch-none overflow-hidden rounded-lg"
        + " bg-[#1b1f2a] ring-1 ring-black/40 ring-inset";
    screen.addEventListener("pointerdown", on.down);
    screen.addEventListener("pointermove", on.move);
    screen.addEventListener("pointerup", on.up);
    screen.addEventListener("pointercancel", on.up);

    const canvas = document.createElement("canvas");
    canvas.className = "absolute inset-0 h-full w-full";
    canvas.setAttribute("aria-hidden", "true");

    const shade = (side) => {
        const element = document.createElement("div");
        element.className = `pointer-events-none absolute inset-y-0 ${side} bg-[#12151d]/75`;
        element.style.width = "0%";
        return element;
    };
    const shadeHead = shade("left-0");
    const shadeTail = shade("right-0");

    const note = document.createElement("p");
    note.className = "pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2"
        + " text-center font-mono text-[7pt] text-white/40";

    screen.append(canvas, shadeHead, shadeTail, note);

    // The playheads. Short and centred on the axis so they read as a position
    // rather than as a third thing to drag, and dimmer than the crop markers,
    // which are what this panel is actually for. No name on them — the running
    // timecode above each one says everything they have to say.
    const playheads = [];
    for (let slot = 0; slot < MAX_PLAYHEADS; slot += 1) {
        const root = document.createElement("div");
        root.className = "pointer-events-none absolute top-1/2 left-0 flex -translate-x-1/2"
            + " -translate-y-1/2 flex-col items-center gap-1";
        root.style.display = "none";

        const label = document.createElement("span");
        label.className = "rounded bg-black/55 px-1 py-px font-mono text-[6.5pt]"
            + " leading-none text-white/75";

        const tick = document.createElement("span");
        tick.className = "h-10 w-px rounded-full bg-white/70";

        root.append(label, tick);
        screen.append(root);
        playheads.push({ root, label, width: 0, measured: -1 });
    }

    const handles = {};
    const labels = {};
    for (const { key, label, edge } of HANDLES) {
        // Wider than the line it draws, so it can be grabbed on a phone.
        const handle = document.createElement("div");
        handle.className = "absolute inset-y-0 w-6 -translate-x-1/2 cursor-ew-resize"
            + " focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning";
        handle.dataset.trimHandle = key;
        handle.tabIndex = 0;
        handle.setAttribute("role", "slider");
        handle.setAttribute("aria-label", `${label} of the kept region, in seconds`);
        handle.setAttribute("aria-valuemin", "0");
        handle.addEventListener("keydown", (event) => on.key(event, key));

        const line = document.createElement("div");
        line.className = "absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 rounded-full"
            + " bg-white shadow-[0_0_6px_rgba(0,0,0,0.7)]";

        // Start's label rides the top edge and End's the bottom, so two markers
        // dragged together never sit their labels on each other.
        // left-1/2 sits the pill's own left edge on the marker line, which is
        // the origin `place` measures its clamp from.
        const pill = document.createElement("div");
        pill.className = "absolute left-1/2 flex items-baseline gap-1 whitespace-nowrap rounded-full"
            + " bg-white px-2 py-0.5 font-mono text-[7pt] text-[#1b1f2a] shadow"
            + (edge === "top" ? " top-1.5" : " bottom-1.5");
        const name = document.createElement("span");
        name.className = "font-bold uppercase tracking-widest opacity-50";
        name.textContent = label;
        const time = document.createElement("span");
        pill.append(name, time);

        handle.append(line, pill);
        screen.append(handle);
        handles[key] = handle;
        labels[key] = time;
    }

    // The ruler under the panel: the two ends of the file, as in a DAW.
    const ruler = document.createElement("div");
    ruler.className = "flex items-baseline justify-between font-mono text-[7pt] opacity-50";
    const head = document.createElement("span");
    head.textContent = clockText(0);
    const total = document.createElement("span");
    ruler.append(head, total);

    root.append(screen, ruler);
    return { screen, canvas, shadeHead, shadeTail, note, handles, labels, playheads, total };
}
