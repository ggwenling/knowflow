import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readBoundedBody } from '../src/lib/bounded-body.ts';

const signal = () => new AbortController().signal;
function stream(chunks, onCancel = () => {}) { return new ReadableStream({start(controller) { for (const bytes of chunks) controller.enqueue(Uint8Array.from(bytes)); controller.close(); }, cancel: onCancel}); }

test('null and empty bodies are supported', async () => {
  assert.equal((await readBoundedBody(null, signal(), 32)).length, 0);
  assert.equal((await readBoundedBody(stream([]), signal(), 32)).length, 0);
});
test('preserves bytes across buffer growth and misleading declared lengths', async () => {
  for (const declared of [0, 1, 30]) {
    const result = await readBoundedBody(stream([[1,2,3], [4,5], [6,7,8,9]]), signal(), 32, declared);
    assert.deepEqual([...result], [1,2,3,4,5,6,7,8,9]);
    assert.ok(result.buffer.byteLength <= 32);
    const request = new Request('http://localhost/upload', {method:'POST',body:result});
    assert.deepEqual([...new Uint8Array(await request.arrayBuffer())], [...result]);
  }
});
test('accepts the exact limit and rejects a chunked overflow before forwarding', async () => {
  assert.equal((await readBoundedBody(stream([[1,2],[3,4]]), signal(), 4)).length, 4);
  assert.equal(await readBoundedBody(stream([[1,2],[3,4,5]]), signal(), 4), null);
});
test('abort cancels a blocked reader and releases its lock', async () => {
  const controller = new AbortController(); let cancelled = false;
  const body = new ReadableStream({pull() {}, cancel() { cancelled = true; }});
  const result = readBoundedBody(body, controller.signal, 32);
  controller.abort();
  await assert.rejects(result, {name:'AbortError'});
  assert.equal(cancelled, true); assert.equal(body.locked, false);
});
