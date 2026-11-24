import assert from "node:assert/strict";
import test from "node:test";
import { peers, standing, tile } from "../components/scores";

const look = (score: number | null, scores: (number | null)[]) => tile(score, peers(scores));
const say = (score: number, scores: (number | null)[]) => standing(score, peers(scores), "Best overall");

test("the single best score is the leader and is named as best", () => {
  assert.deepEqual(look(0.96, [0.96, 0.83, null]), { "data-empty": false, "data-tone": "leader" });
  assert.equal(say(0.96, [0.96, 0.83, null]), "Best overall");
});

test("scores that round to the same best percentage are tied leaders", () => {
  assert.deepEqual(look(0.781, [0.781, 0.782, 0.5]), { "data-empty": false, "data-tone": "leader" });
  assert.deepEqual(look(0.782, [0.781, 0.782, 0.5]), { "data-empty": false, "data-tone": "leader" });
  assert.equal(say(0.782, [0.781, 0.782, 0.5]), "Tied for best");
});

test("a trailing score fades by its gap to the best, in whole percentage points", () => {
  // gap 13: 100 * exp(-13 / 28) = 62.9
  assert.deepEqual(look(0.83, [0.96, 0.83]), { "data-empty": false, "data-tone": "trail", style: { "--heat": "62.9%" } });
  assert.equal(say(0.83, [0.96, 0.83]), "−13 pts · best 96%");
  // Both show 78%, so both get the same color.
  assert.deepEqual(look(0.781, [0.9, 0.781]), look(0.776, [0.9, 0.776]));
  assert.equal(say(0.49, [0.5, 0.49]), "−1 pt · best 50%");
});

test("a score more than 50 points behind the best gets muted ink", () => {
  assert.equal(look(0.3, [0.9, 0.3])["data-tone"], "far");
  assert.equal(look(0.4, [0.9, 0.4])["data-tone"], "trail");
});

test("a 0% score is never a leader, whether or not another score is above it", () => {
  assert.deepEqual(look(0, [0, 0]), { "data-empty": false, "data-tone": "zero" });
  assert.equal(say(0, [0, 0]), "No model scored");
  assert.deepEqual(look(0, [0.13, 0.06, 0]), { "data-empty": false, "data-tone": "zero" });
  assert.equal(say(0, [0.13, 0.06, 0]), "−13 pts · best 13%");
});

test("a tile without a score is empty and has no color", () => {
  assert.deepEqual(look(null, [0.5, null]), { "data-empty": true });
  assert.deepEqual(look(null, [null, null]), { "data-empty": true });
});
