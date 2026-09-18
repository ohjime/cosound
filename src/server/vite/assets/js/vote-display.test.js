import test from "node:test";
import assert from "node:assert/strict";
import { voteDisplay } from "./vote-display.js";

test("vote card opens from playback and stays closed during cooldown", () => {
    const display = voteDisplay([{ sound_id: 1, sound_gain: 1 }]);
    display.$el = { dataset: { voteChoice: "1" } };
    display.openVoteCard();
    assert.equal(display.activeVote, true);
    display.activeVote = false;
    display.secondsLeft = 30;
    display.openVoteCard();
    assert.equal(display.activeVote, false);
});

const layers = [
    { sound_id: 11, sound_title: "Rain", sound_artist: "Artist", sound_gain: 0.35, saved: false },
    { sound_id: 22, sound_title: "Bells", sound_gain: 0, saved: false },
];

test("a sound-only carousel starts at layer one and preserves the venue's gains", () => {
    const display = voteDisplay(layers);
    const original = display.layers.map((layer) => layer.sound_gain);
    assert.equal(display.currentLayer.sound_id, 11);
    assert.equal(display.gainPercent, 35);
    display.move(-1);
    assert.equal(display.currentIndex, 0);
    display.move(1);
    assert.equal(display.currentLayer.sound_id, 22);
    assert.equal(display.gainPercent, 0);
    display.move(1);
    assert.equal(display.currentIndex, 1);
    assert.deepEqual(display.layers.map((layer) => layer.sound_gain), original);
});

test("volume readout stays within 0–100 and rounds to whole percentages", () => {
    const display = voteDisplay([
        { sound_id: 1, sound_gain: 0 },
        { sound_id: 2, sound_gain: 0.075 },
        { sound_id: 3, sound_gain: 0.75 },
        { sound_id: 4, sound_gain: 1 },
    ]);
    assert.deepEqual(display.carouselSlides.map((_, index) => {
        display.select(index);
        return display.gainPercent;
    }), [0, 8, 75, 100]);
});

test("layer indicator shade reflects each layer's gain", () => {
    const display = voteDisplay([
        { sound_id: 1, sound_gain: 0 },
        { sound_id: 2, sound_gain: 0.75 },
        { sound_id: 3, sound_gain: 1 },
    ]);
    assert.deepEqual(display.carouselSlides.map((slide) => display.layerIndicatorOpacity(slide)), [0.5, 0.875, 1]);
});

test("swiping the artwork changes the selected layer", () => {
    const display = voteDisplay(layers);
    const carousel = {
        scrollLeft: 295,
        querySelectorAll: () => [{ offsetLeft: 0 }, { offsetLeft: 300 }],
        scrollTo: ({ left }) => { carousel.scrollLeft = left; },
    };
    display.$refs = { carousel };
    display.updateActive();
    assert.equal(display.currentIndex, 1);
    display.move(-1);
    assert.equal(carousel.scrollLeft, 0);
});

test("a delayed like response updates its sound even after moving to another layer", () => {
    const display = voteDisplay(layers);
    display.move(1);
    display.onLayerSaved({ soundId: "11", saved: true });
    assert.equal(display.layers[0].saved, true);
    assert.equal(display.currentLayer.saved, false);
    assert.equal(layers[0].saved, false);
    display.onLayerSaved({ soundId: "99", saved: true });
    assert.equal(display.layers.length, 2);
});

test("saving sends the exact snapshot IDs and gains with the post title", () => {
    const display = voteDisplay(layers);
    display.title = 'Rain & "bells"';
    const payload = JSON.parse(display.savePayload());
    assert.equal(payload.title, display.title);
    assert.deepEqual(JSON.parse(payload.layers), [
        { sound_id: 11, sound_gain: 0.35 },
        { sound_id: 22, sound_gain: 0 },
    ]);
});

test("initialization reads only the card's metadata payload", () => {
    const display = voteDisplay();
    display.$el = {
        dataset: { postTitle: "Venue post", hasVoteAction: "false" },
        querySelector: () => ({ textContent: JSON.stringify(layers) }),
    };
    display.init();
    assert.equal(display.title, "Venue post");
    assert.equal(display.currentLayer.sound_title, "Rain");
});

test("choice URLs preset Pleasant while the slider can reverse the vote", () => {
    for (const [choice, expected] of [["0", 0], ["1", 1]]) {
        const display = voteDisplay();
        display.$el = { dataset: { voteChoice: choice }, querySelector: () => null };
        display.init();
        assert.equal(display.pleasant, expected);
        assert.deepEqual(JSON.parse(display.pleasantPayload), { pleasant: expected });
        display.pleasant = 1 - expected;
        assert.deepEqual(JSON.parse(display.pleasantPayload), { pleasant: 1 - expected });
        assert.equal(display.voteLabel, expected === 1 ? "DOWNVOTE" : "UPVOTE");
    }
});

test("vote slider stays where released and changes the vote at halfway", () => {
    const display = voteDisplay();
    display.updateVoteSlider("0.38");
    assert.equal(display.voteSlider, 0.38);
    assert.equal(display.pleasant, 0);
    display.updateVoteSlider(0.5);
    assert.equal(display.pleasant, 1);
    assert.equal(display.voteSlider, 0.5);
    display.updateVoteSlider(0.67);
    assert.equal(display.voteSlider, 0.67);
});

test("thumb buttons move both the vote and its range input", () => {
    const display = voteDisplay();
    const input = { value: "0.38" };
    display.$refs = { voteRange: input };
    display.setVoteChoice(0);
    assert.equal(display.pleasant, 0);
    assert.equal(display.voteSlider, 0);
    assert.equal(input.value, "0");
    display.setVoteChoice(1);
    assert.equal(display.pleasant, 1);
    assert.equal(display.voteSlider, 1);
    assert.equal(input.value, "1");
});

test("vote submission includes the chosen direction and guest identity", () => {
    const display = voteDisplay();
    display.$el = { dataset: { authenticated: "false" } };
    display.setVoteChoice(0);
    assert.deepEqual(JSON.parse(display.submissionPayload), { pleasant: 0, anonymous: "1" });
    display.voteAnonymously = false;
    assert.deepEqual(JSON.parse(display.submissionPayload), { pleasant: 0 });
    display.$el.dataset.authenticated = "true";
    assert.deepEqual(JSON.parse(display.submissionPayload), { pleasant: 0 });
});

test("empty and malformed predictions remain safe to render", () => {
    const display = voteDisplay();
    display.$el = { dataset: {}, querySelector: () => ({ textContent: "invalid" }) };
    display.init();
    display.move(1);
    display.updateActive();
    assert.equal(display.currentIndex, 0);
    assert.equal(display.currentLayer, null);
    assert.equal(display.currentSlide, null);
    assert.deepEqual(display.carouselSlides, []);
    assert.equal(display.gainPercent, 0);
    assert.equal(display.isEmpty, true);
    assert.equal(display.activationMode, false);
    assert.equal(display.voteLabel, "UPVOTE");
    assert.equal(display.isFirst, true);
    assert.equal(display.isLast, true);
    assert.deepEqual(JSON.parse(JSON.parse(display.savePayload()).layers), []);
});

test("the playing card carousel contains only sound layers when voting is available", () => {
    const display = voteDisplay(layers);
    display.pleasant = 1;

    assert.deepEqual(
        display.carouselSlides.map((slide) => slide.kind),
        ["layer", "layer"],
    );
    assert.deepEqual(
        display.carouselSlides.map((slide) => slide.indicatorLabel),
        ["1", "2"],
    );
    assert.equal(display.currentLayer.sound_id, 11);

    display.move(1);
    assert.equal(display.currentLayer.sound_id, 22);
    assert.equal(display.gainPercent, 0);
});

test("an awake empty venue has no sound layers in its playing card", () => {
    const display = voteDisplay();

    assert.deepEqual(display.carouselSlides, []);
    assert.equal(display.currentSlide, null);
    display.move(1);
    assert.equal(display.currentSlide, null);
    assert.equal(display.currentLayer, null);
    assert.equal(display.isLast, true);
});

test("sleeping metadata enables activation even when stale layers are present", () => {
    const display = voteDisplay(layers);
    display.$el = {
        dataset: { playerSleeping: "true", hasVoteAction: "true" },
        querySelector: () => ({ textContent: JSON.stringify(layers) }),
    };
    display.init();

    assert.equal(display.playerSleeping, true);
    assert.equal(display.activationMode, true);
    assert.equal(display.voteLabel, "ACTIVATE");
    assert.deepEqual(display.carouselSlides, []);
});

test("activation success keeps the confirmation view and accepts fresh layers", () => {
    const display = voteDisplay([], true);
    display.handlePlayerActivated({ layers });

    assert.equal(display.playerSleeping, false);
    assert.equal(display.activationMode, true);
    assert.equal(display.activationComplete, true);
    assert.equal(display.activationError, "");
    assert.deepEqual(display.layers, layers);
    assert.notEqual(display.layers[0], layers[0]);
    assert.deepEqual(display.carouselSlides, []);
});

test("a room that sleeps after rendering an active card keeps its normal carousel when woken", () => {
    const display = voteDisplay(layers);
    const replacement = [{ ...layers[1], sound_id: 33, sound_title: "Wind" }];

    display.handlePlayerActivated({ layers: replacement });

    assert.equal(display.renderedActivationCard, false);
    assert.equal(display.activationMode, false);
    assert.equal(display.activationComplete, false);
    assert.deepEqual(
        display.carouselSlides.map((slide) => slide.kind),
        ["layer"],
    );
    assert.equal(display.layers[0].sound_id, 33);
});

test("an unavailable wake on an already-rendered active card reloads into activation UI", () => {
    const display = voteDisplay(layers);
    let reloads = 0;
    display.reloadForActivation = () => { reloads += 1; };

    display.handleActivationUnavailable();

    assert.equal(reloads, 1);
    assert.equal(display.activationMode, false);
});

test("unavailable activation stays actionable and shows a calm message", () => {
    const display = voteDisplay([], true);
    display.handleActivationUnavailable({ message: "Add sounds to this room first." });

    assert.equal(display.activationMode, true);
    assert.equal(display.activationComplete, false);
    assert.equal(display.activationError, "Add sounds to this room first.");
    display.handleActivationUnavailable();
    assert.equal(display.activationError, "This room has no sounds available yet.");
});

test("anonymous vote authentication errors stay on the vote presentation", () => {
    const display = voteDisplay(layers);
    display.handleVoteAuthUnavailable({ message: "Try that vote again." });

    assert.equal(display.activationMode, false);
    assert.equal(display.voteError, "Try that vote again.");
    display.handleVoteSuccess();
    assert.equal(display.voteError, "");
});

test("vote success and throttling drive the card labels", () => {
    const display = voteDisplay(layers);
    display.pleasant = 1;
    assert.equal(display.voteLabel, "UPVOTE");
    assert.equal(display.votePastLabel, "Upvoted");
    const kindsBeforeVote = display.carouselSlides.map((slide) => slide.kind);
    display.handleVoteSuccess();
    assert.equal(display.voted, true);
    assert.equal(display.secondsLeft, 0);
    assert.equal(display.currentIndex, 0);
    assert.deepEqual(display.carouselSlides.map((slide) => slide.kind), kindsBeforeVote);

    const downvote = voteDisplay(layers);
    downvote.pleasant = 0;
    assert.equal(downvote.voteLabel, "DOWNVOTE");
    assert.equal(downvote.votePastLabel, "Downvoted");
    downvote.handleThrottle(12);
    assert.equal(downvote.secondsLeft, 12);
    clearInterval(downvote.timer);
});

test("active vote spacing ends after the prompt card leaves the stack", () => {
    const display = voteDisplay(layers);
    display.$el = { dataset: { voteActive: "true" }, querySelector: () => null };
    display.init();
    assert.equal(display.activeVote, true);
    display.handleVoteSuccess();
    assert.equal(display.activeVote, true);
    display.handleCardRemoved({ card: { querySelector: () => ({}) } });
    assert.equal(display.activeVote, false);

    const throttled = voteDisplay(layers);
    throttled.$el = { dataset: { voteActive: "true" }, querySelector: () => null };
    throttled.init();
    throttled.handleThrottle(12);
    assert.equal(throttled.activeVote, true);
    throttled.handleCardRemoved({ card: { querySelector: () => ({}) } });
    assert.equal(throttled.activeVote, false);
    throttled.destroy();
});

test("trying the fixed public volume shows a temporary notice", () => {
    const display = voteDisplay(layers);
    display.showVolumeNotice();
    assert.equal(display.volumeNotice, true);
    assert.notEqual(display.volumeNoticeTimer, null);
    display.showVolumeNotice();
    display.destroy();
});
