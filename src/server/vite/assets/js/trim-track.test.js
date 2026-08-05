import test from "node:test";
import assert from "node:assert/strict";

import { peaksFromBuffer } from "./soundscape-mixer.js";
import { clockText } from "./trim-track.js";

// Just enough AudioBuffer for the envelope walk: channel data and a length.
function fakeBuffer(channels, sampleRate = 48000) {
    const data = channels.map((values) => Float32Array.from(values));
    return {
        numberOfChannels: data.length,
        length: data[0].length,
        sampleRate,
        duration: data[0].length / sampleRate,
        getChannelData: (index) => data[index],
    };
}

test("peaksFromBuffer summarises each bucket by its extremes", () => {
    // Four samples, two buckets: one bucket per pair. Quarters, so Float32
    // holds them exactly and the assertions can be about the walk, not rounding.
    const peaks = peaksFromBuffer(fakeBuffer([[0.25, -0.5, 0.75, -0.25]]), 2);
    assert.deepEqual(Array.from(peaks.max), [0.25, 0.75]);
    assert.deepEqual(Array.from(peaks.min), [-0.5, -0.25]);
    assert.equal(peaks.peak, 0.75);
    assert.equal(peaks.length, 2);
});

test("peaksFromBuffer takes the extremes across every channel", () => {
    // Float32Array rounds what it is given, so compare at its precision.
    const peaks = peaksFromBuffer(fakeBuffer([[0.2, 0.2], [-0.9, -0.9]]), 1);
    assert.equal(peaks.max[0], Math.fround(0.2));
    assert.equal(peaks.min[0], Math.fround(-0.9));
    // The peak is a magnitude, so the loud negative channel sets it.
    assert.equal(peaks.peak, Math.fround(0.9));
});

test("peaksFromBuffer fills every bucket asked for, however short the file", () => {
    // More buckets than samples: the buckets past the end must still exist, or
    // the renderer would read undefined out of them.
    const peaks = peaksFromBuffer(fakeBuffer([[1, -1]]), 8);
    assert.equal(peaks.length, 8);
    assert.equal(peaks.min.length, 8);
    assert.equal(peaks.max.length, 8);
    assert.ok(peaks.max.every((value) => Number.isFinite(value)));
});

test("peaksFromBuffer returns a drawable empty envelope for silence", () => {
    const peaks = peaksFromBuffer(fakeBuffer([[0, 0, 0, 0]]), 4);
    assert.equal(peaks.peak, 0);
    assert.deepEqual(Array.from(peaks.max), [0, 0, 0, 0]);
});

test("peaksFromBuffer survives a layer with no buffer at all", () => {
    const peaks = peaksFromBuffer(null, 4);
    assert.equal(peaks.peak, 0);
    assert.equal(peaks.length, 4);
});

test("peaksFromBuffer keeps the envelope of a bucket it has to subsample", () => {
    // Past PEAK_SAMPLE_LIMIT a bucket is strided. The signal oscillates, so the
    // extremes still land in the stride and the envelope holds.
    const samples = new Float32Array(200000);
    for (let i = 0; i < samples.length; i += 1) samples[i] = Math.sin(i / 7);
    const peaks = peaksFromBuffer(fakeBuffer([samples]), 16);
    assert.ok(peaks.peak > 0.99, `expected a full-scale peak, got ${peaks.peak}`);
    assert.ok(Array.from(peaks.min).every((value) => value < -0.9));
});

test("clockText reads to the millisecond, zero-padded", () => {
    assert.equal(clockText(0), "0:00.000");
    assert.equal(clockText(2.612), "0:02.612");
    assert.equal(clockText(3.529), "0:03.529");
    assert.equal(clockText(61.5), "1:01.500");
    assert.equal(clockText(600), "10:00.000");
});

test("clockText refuses to print a negative or missing time", () => {
    assert.equal(clockText(-4), "0:00.000");
    assert.equal(clockText(undefined), "0:00.000");
    assert.equal(clockText(NaN), "0:00.000");
});
