import assert from "node:assert/strict";
import test from "node:test";

import { voteCountdown } from "./vote-countdown.js";

test("vote heading tracks the server cooldown and switches after activation", () => {
    const countdown = voteCountdown(0, true);
    assert.equal(countdown.sleeping, true);
    countdown.onPlayerActivated();
    assert.equal(countdown.sleeping, false);

    countdown.onVoteSuccess({ seconds_left: 65 });
    assert.equal(countdown.minutes, 1);
    assert.equal(countdown.seconds, 5);
    countdown.onThrottle({ seconds_left: 12 });
    assert.equal(countdown.minutes, 0);
    assert.equal(countdown.seconds, 12);
    countdown.destroy();
});

test("expired cooldown refreshes the vote section so the card returns", () => {
    const countdown = voteCountdown();
    const originalHtmx = globalThis.htmx;
    const requests = [];
    globalThis.htmx = { ajax: (...args) => requests.push(args) };
    countdown.$el = { dataset: { refreshUrl: "/vote/tab/?player=room" } };
    try {
        countdown.start(1);
        countdown.deadline = Date.now() - 1;
        countdown.tick();
        assert.equal(countdown.secondsLeft, 0);
        assert.deepEqual(requests, [["GET", "/vote/tab/?player=room", { target: "#vote-tab-content", swap: "innerHTML" }]]);
    } finally {
        countdown.destroy();
        globalThis.htmx = originalHtmx;
    }
});
