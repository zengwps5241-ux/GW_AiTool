import assert from "node:assert/strict";
import {
  getCommandTrigger,
  isCommandSelectionKey,
  replaceCommandTrigger,
} from "../src/lib/commandMenu";

const sentence = "/superpowers:writing-plans 编写计划 /super";
const trigger = getCommandTrigger(sentence, sentence.length);
assert.ok(trigger);

assert.deepEqual(trigger, {
  start: 32,
  end: sentence.length,
  query: "super",
});

assert.equal(
  replaceCommandTrigger(sentence, trigger, "superpowers:executing-plans"),
  "/superpowers:writing-plans 编写计划 /superpowers:executing-plans ",
);

const middle = "请先 /super 后面还有文字";
const middleTrigger = getCommandTrigger(middle, "请先 /super".length);
assert.ok(middleTrigger);
assert.deepEqual(middleTrigger, {
  start: 3,
  end: "请先 /super".length,
  query: "super",
});

assert.equal(
  replaceCommandTrigger(middle, middleTrigger, "superpowers:writing-plans"),
  "请先 /superpowers:writing-plans 后面还有文字",
);

assert.equal(isCommandSelectionKey("Enter"), true);
assert.equal(isCommandSelectionKey("Tab"), true);
assert.equal(isCommandSelectionKey("ArrowDown"), false);
