import assert from "node:assert/strict";
import test from "node:test";

import { createLatestQueue } from "../src/utils/latestQueue.js";


test("serializes writes and keeps only latest pending value", async () => {
  const written = [];
  let releaseFirst;
  const firstBlocked = new Promise((resolve) => { releaseFirst = resolve; });
  const enqueue = createLatestQueue(async (value) => {
    written.push(value);
    if (value === 1) await firstBlocked;
  });

  const complete = enqueue(1);
  enqueue(2);
  enqueue(3);
  releaseFirst();
  await complete;

  assert.deepEqual(written, [1, 3]);
});


test("continues with pending value after failed write", async () => {
  const written = [];
  let releaseFirst;
  const firstBlocked = new Promise((resolve) => { releaseFirst = resolve; });
  const enqueue = createLatestQueue(async (value) => {
    written.push(value);
    if (value === "first") {
      await firstBlocked;
      throw new Error("failed");
    }
  });

  const failed = enqueue("first");
  enqueue("latest");
  releaseFirst();
  await assert.rejects(failed, /failed/);
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.deepEqual(written, ["first", "latest"]);
});


test("flush waits for active and pending writes", async () => {
  const written = [];
  let releaseFirst;
  const firstBlocked = new Promise((resolve) => { releaseFirst = resolve; });
  const enqueue = createLatestQueue(async (value) => {
    if (value === 1) await firstBlocked;
    written.push(value);
  });

  enqueue(1);
  enqueue(2);
  const flushed = enqueue.flush();
  releaseFirst();
  await flushed;

  assert.deepEqual(written, [1, 2]);
});
