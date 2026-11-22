const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const editor = {};
const source = readFileSync(join(__dirname, "../spritewaffle/ui/static/pixel_editor.js"), "utf8");
vm.runInNewContext(source, editor);

const A = 0x445566ff, TRANSLUCENT = 0x44556680, CLEAR = 0x00000000, HIDDEN = 0x44556600;
const INK = 0xff9900ff;

function image(rows) {
  const pixels = new DataView(new ArrayBuffer(rows.length * rows[0].length * 4));
  rows.flat().forEach((value, i) => pixels.setUint32(i * 4, value));
  return pixels;
}

function fill(rows, a, b, seed, paint = INK) {
  const pixels = image(rows);
  const indices = editor.pixelFillOffsets(pixels, rows[0].length, editor.pixelRectangle(a, b), seed, paint);
  return Array.from(indices, offset => offset / 4).sort((x, y) => x - y);
}

test("normalizes inclusive selection corners in either direction", () => {
  const bounds = editor.pixelRectangle([4, 1], [1, 5]);
  assert.deepEqual({...bounds}, {left: 1, top: 1, right: 4, bottom: 5});
  const single = editor.pixelRectangle([2, 3], [2, 3]);
  assert.deepEqual({...single}, {left: 2, top: 3, right: 2, bottom: 3});
});

test("fills four-way neighbors without crossing diagonals or alpha boundaries", () => {
  const rows = [[A, A, TRANSLUCENT, A], [A, CLEAR, A, A], [TRANSLUCENT, A, A, A]];
  assert.deepEqual(fill(rows, [0, 0], [3, 2], [0, 0]), [0, 1, 4]);
});

test("keeps exact RGB when matching fully transparent pixels", () => {
  assert.deepEqual(fill([[CLEAR, HIDDEN, CLEAR]], [0, 0], [2, 0], [0, 0]), [0]);
});

test("does not treat the ends of adjacent rows as neighbors", () => {
  assert.deepEqual(fill([[CLEAR, CLEAR, A], [A, CLEAR, CLEAR]], [0, 0], [2, 1], [2, 0]), [2]);
});

test("clips fill and its seed to the selection and treats the same RGBA as a no-op", () => {
  const rows = [[A, A, A], [A, A, A], [A, A, A]];
  assert.deepEqual(fill(rows, [2, 1], [1, 0], [2, 1]), [1, 2, 4, 5]);
  assert.deepEqual(fill(rows, [2, 1], [1, 0], [0, 0]), []);
  assert.deepEqual(fill(rows, [2, 1], [1, 0], [2, 1], A), []);
});

test("handles a full 384 by 384 processed cell without recursion", () => {
  const edge = 384;
  const pixels = new DataView(new ArrayBuffer(edge * edge * 4));
  const bounds = editor.pixelRectangle([0, 0], [edge - 1, edge - 1]);
  const indices = editor.pixelFillOffsets(pixels, edge, bounds, [0, 0], INK);
  assert.equal(indices.length, edge * edge);
  assert.equal(new Set(indices).size, indices.length);
  assert.equal(indices.at(-1), (edge * edge - 1) * 4);
  assert.equal(pixels.getUint32(0), CLEAR);
});
