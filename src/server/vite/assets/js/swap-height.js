/**
 * Height-animated htmx swaps.
 *
 * The home page's column is vertically centred (`min-h-dvh … justify-center`),
 * so its height is the only thing holding the core header and the tab bar where
 * they are. Swap a tab body of a different height into that column and the
 * whole thing re-centres in a single frame: pick a short tab and the header
 * visibly drops, because the content under it collapsed out from beneath it.
 *
 * Marking a swap target with `data-swap-height` makes it animate from the
 * height it had to the height its new content wants, so the re-centring is
 * spread over a few hundred milliseconds instead of happening between two
 * frames. Nothing about the layout changes — the element still sizes to its
 * content the moment the animation is done.
 */

// Change of 1px costs this much animation time, clamped to the range below —
// a small swap should not take as long as a swap into a full article.
const MS_PER_PX = 0.45;
const MIN_DURATION_MS = 200;
const MAX_DURATION_MS = 450;

// Height changes smaller than this are not worth animating (or noticing).
const MIN_DELTA_PX = 2;

const EASING = "cubic-bezier(0.22, 1, 0.36, 1)";

const ATTRIBUTE = "data-swap-height";

// Height each element had when its swap started, and the animation currently
// playing on it — a second swap mid-animation has to interrupt the first.
const outgoingHeight = new WeakMap();
const playing = new WeakMap();

/** How long a swap that changes an element's height by `delta` px should take. */
export function swapDuration(delta) {
    const distance = Math.abs(delta);
    return Math.min(
        MAX_DURATION_MS,
        Math.max(MIN_DURATION_MS, Math.round(distance * MS_PER_PX)),
    );
}

// htmx fires these events on the target in some paths and on the requesting
// element in others, and passes the target in the detail either way, so look in
// both places before giving up.
function resolveTarget(event) {
    const candidates = [event.detail && event.detail.target, event.target];
    for (const el of candidates) {
        if (el && el.nodeType === 1 && el.hasAttribute(ATTRIBUTE)) return el;
    }
    return null;
}

function height(el) {
    return el.getBoundingClientRect().height;
}

export function installSwapHeightTransitions({
    root = document,
    scroller = typeof window === "undefined" ? null : window,
} = {}) {
    root.addEventListener("htmx:beforeSwap", (event) => {
        const el = resolveTarget(event);
        if (!el) return;
        // Read the height that is on screen right now — mid-animation that is
        // the animated height, not the old content's natural one.
        outgoingHeight.set(el, height(el));
    });

    root.addEventListener("htmx:afterSwap", (event) => {
        const el = resolveTarget(event);
        if (!el || !outgoingHeight.has(el)) return;
        const from = outgoingHeight.get(el);
        outgoingHeight.delete(el);

        // A tab swapped while scrolled into the outgoing body leaves the
        // viewport parked in whatever the new body has (or hasn't) got there.
        // Land back at the top, the way arriving on the tab would have.
        if (scroller && scroller.scrollY > 0) scroller.scrollTo(0, 0);

        const running = playing.get(el);
        if (running) {
            running.cancel();
            playing.delete(el);
        }

        if (typeof el.animate !== "function") return;
        if (
            root.defaultView &&
            root.defaultView.matchMedia &&
            root.defaultView.matchMedia("(prefers-reduced-motion: reduce)")
                .matches
        ) {
            return;
        }

        // With the animation cancelled and no inline height left, this is the
        // height the new content settles at.
        const to = height(el);
        if (Math.abs(to - from) < MIN_DELTA_PX) return;

        const previousOverflow = el.style.overflow;
        el.style.overflow = "hidden";

        // No `fill`: when the animation ends the element is back to sizing
        // itself, so anything that loads late (images, the article's video)
        // still grows it normally.
        const animation = el.animate(
            [{ height: `${from}px` }, { height: `${to}px` }],
            { duration: swapDuration(to - from), easing: EASING },
        );
        playing.set(el, animation);

        const release = () => {
            if (playing.get(el) === animation) playing.delete(el);
            el.style.overflow = previousOverflow;
        };
        if (animation.finished) {
            animation.finished.then(release, release);
        } else {
            animation.onfinish = release;
            animation.oncancel = release;
        }
    });
}
