import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getEventListeners } from 'node:events';
import { RequestScope, abortableDelay, waitUntilVisible } from '../src/lib/request-scope.ts';

test('limits total concurrency while completing every operation', async () => {
  const scope = new RequestScope(3); let running = 0; let peak = 0;
  const results = await Promise.all(Array.from({length: 20}, (_, i) => scope.run(async () => {
    running++; peak = Math.max(peak, running);
    await abortableDelay(2, scope.signal); running--; return i;
  })));
  assert.equal(peak, 3); assert.equal(results.length, 20);
  assert.equal(getEventListeners(scope.signal, 'abort').length, 1);
  scope.abort();
});

test('abort rejects running and queued work without starting queued operations', async () => {
  const scope = new RequestScope(2); let started = 0;
  const result = Promise.allSettled(Array.from({length: 8}, () => scope.run(async () => { started++; await abortableDelay(10_000, scope.signal); })));
  await Promise.resolve(); scope.abort();
  assert.equal(started, 2);
  assert.ok((await result).every(item => item.status === 'rejected' && item.reason.name === 'AbortError'));
  await assert.rejects(scope.run(async () => 1), {name: 'AbortError'});
  assert.equal(getEventListeners(scope.signal, 'abort').length, 0);
});

test('individual cancellation releases a queued task without affecting others', async () => {
  const scope = new RequestScope(1); const task = new AbortController();
  let release; const gate = new Promise(resolve => { release = resolve; });
  const first = scope.run(() => gate);
  let ran = false; const queued = scope.run(async () => { ran = true; }, task.signal);
  const cancelled = assert.rejects(queued, {name: 'AbortError'});
  task.abort(); release(1); await first; await cancelled;
  assert.equal(ran, false); assert.equal(getEventListeners(task.signal, 'abort').length, 0); scope.abort();
});

test('delay and visibility reject already cancelled scopes', async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(abortableDelay(1, controller.signal), {name: 'AbortError'});
  await assert.rejects(waitUntilVisible(controller.signal), {name: 'AbortError'});
});
