const assert = require("node:assert/strict");
const test = require("node:test");
const {tileFrameAt} = require("../spritewaffle/ui/static/tileset_animation.js");

test("tile playback holds each frame for its duration and wraps to the first", () => {
  const frames = [{tile: 5, duration_ms: 70}, {tile: 2, duration_ms: 230}, {tile: 1, duration_ms: 25}];
  const samples = [-1, 0, 69, 70, 299, 300, 324, 325, 395, 650];
  assert.deepEqual(samples.map(time => tileFrameAt(frames, time)), [5, 5, 5, 2, 2, 1, 1, 5, 2, 5]);
});

test("static tiles use their own ID and frame zero is valid artwork", () => {
  assert.equal(tileFrameAt([], 5000), null);
  assert.equal(tileFrameAt([{tile: 0, duration_ms: 12}, {tile: 1, duration_ms: 36}], 0), 0);
});
