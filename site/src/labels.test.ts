import assert from "node:assert/strict";
import test from "node:test";
import { unwrapPrompt } from "./labels";

test("prompt display joins hard wraps but keeps paragraphs and lists", () => {
  assert.equal(unwrapPrompt("supply 10k of it? so it\nearns interest.\n"), "supply 10k of it? so it earns interest.");
  assert.equal(unwrapPrompt("first part.\n\nsecond part."), "first part.\n\nsecond part.");
  assert.equal(unwrapPrompt("steps:\n- one\n- two\n1. three"), "steps:\n- one\n- two\n1. three");
});
