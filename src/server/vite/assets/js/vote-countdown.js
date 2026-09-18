/** The vote heading follows the same cooldown returned by the server. */
export function voteCountdown(initialSeconds = 0, initiallySleeping = false) {
    return {
        secondsLeft: Math.max(0, Number(initialSeconds) || 0),
        sleeping: Boolean(initiallySleeping),
        readyToRefresh: false,
        deadline: 0,
        timer: null,

        init() {
            if (this.secondsLeft > 0) this.start(this.secondsLeft);
        },

        destroy() {
            if (this.timer) clearInterval(this.timer);
        },

        get minutes() { return Math.floor(this.secondsLeft / 60); },
        get seconds() { return this.secondsLeft % 60; },

        start(seconds) {
            if (this.timer) clearInterval(this.timer);
            this.secondsLeft = Math.max(0, Number(seconds) || 0);
            this.readyToRefresh = false;
            if (this.secondsLeft === 0) return;
            this.deadline = Date.now() + this.secondsLeft * 1000;
            this.timer = setInterval(() => this.tick(), 250);
        },

        tick() {
            this.secondsLeft = Math.max(0, Math.ceil((this.deadline - Date.now()) / 1000));
            if (this.secondsLeft !== 0) return;
            clearInterval(this.timer);
            this.timer = null;
            this.readyToRefresh = true;
        },

        refresh() {
            globalThis.location?.reload?.();
        },

        onVoteSuccess(detail) {
            this.start(detail?.seconds_left);
        },

        onThrottle(detail) {
            this.start(detail?.seconds_left);
        },

        onPlayerActivated() {
            this.sleeping = false;
        },
    };
}
