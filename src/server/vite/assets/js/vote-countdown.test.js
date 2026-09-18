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

test("expired cooldown offers a manual page refresh", () => {
    const countdown = voteCountdown();
    const originalLocation = globalThis.location;
    let reloads = 0;
    globalThis.location = { reload: () => { reloads += 1; } };
    try {
        countdown.start(1);
        countdown.deadline = Date.now() - 1;
        countdown.tick();
        assert.equal(countdown.secondsLeft, 0);
        assert.equal(countdown.readyToRefresh, true);
        assert.equal(reloads, 0);
        countdown.refresh();
        assert.equal(reloads, 1);
    } finally {
        countdown.destroy();
        globalThis.location = originalLocation;
    }
});
