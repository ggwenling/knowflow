import { test } from 'node:test';
import assert from 'node:assert/strict';
import { streamQuestion } from '../src/services/question-stream.ts';

const frame = (event, sequence, extra = {}) => `event: ${event}\r\ndata: ${JSON.stringify({event, sequence, request_id:'request-1', contract_version:'0.2.0', ...extra})}\r\n\r\n`;
const source = {source_id:'s1',document_id:'d1',content_version_id:'v1',quote:'依据',locator:{kind:'text_range',start:0,end:2,page:null,unit:'unicode_codepoint'}};
const finish = sequence => frame('sources', sequence, {has_answer:true,sources:[source]}) + frame('completed', sequence+1);
function response(text, chunkSize = 17) {
 const bytes = new TextEncoder().encode(text); let offset = 0;
 return new Response(new ReadableStream({pull(controller) {
  if (offset === bytes.length) {controller.close(); return;}
  controller.enqueue(bytes.slice(offset, offset + chunkSize)); offset = Math.min(bytes.length, offset + chunkSize);
 }}), {headers:{'x-request-id':'request-1','content-type':'text/event-stream'}});
}

test('handles CRLF and UTF-8 split at every byte while keeping citations and order', async () => {
 let answer = ''; let sources;
 await streamQuestion(response(frame('started',1) + frame('delta',2,{delta:'中文😀答案'}) + finish(3),1), delta => {answer += delta;}, value => {sources = value;});
 assert.equal(answer,'中文😀答案'); assert.deepEqual(sources,[source]);
});
test('accepts refusal with an empty source set', async () => {
 let hasAnswer;
 await streamQuestion(response(frame('started',1)+frame('sources',2,{has_answer:false,sources:[]})+frame('completed',3)),()=>{},(_,value)=>{hasAnswer=value;});
 assert.equal(hasAnswer,false);
});
for (const [name, body] of [
 ['wrong contract',frame('started',1,{contract_version:'0.1.0'})],
 ['wrong request ID',frame('started',1,{request_id:'other'})],
 ['out-of-order event',frame('started',1)+frame('delta',3,{delta:'x'})],
 ['duplicate event',frame('started',1)+frame('started',2)],
 ['delta before started',frame('delta',1,{delta:'x'})],
 ['completion without sources',frame('started',1)+frame('completed',2)],
 ['delta after sources',frame('started',1)+frame('sources',2,{has_answer:false,sources:[]})+frame('delta',3,{delta:'x'})],
 ['invalid source',frame('started',1)+frame('sources',2,{has_answer:true,sources:[{}]})],
 ['invalid JSON','event: started\ndata: nope\n\n'],
 ['truncated stream',frame('started',1)+frame('delta',2,{delta:'partial'})],
]) test(`rejects ${name} without silently completing`, async () => {await assert.rejects(streamQuestion(response(body),()=>{},()=>{}));});
test('propagates explicit cancellation and server errors', async () => {
 await assert.rejects(streamQuestion(response(frame('started',1)+frame('cancelled',2)),()=>{},()=>{}), {name:'AbortError'});
 await assert.rejects(streamQuestion(response(frame('error',1,{message:'请稍后重试'})),()=>{},()=>{}), /请稍后重试/);
});
test('bounds incomplete frames and releases the reader on failure', async () => {
 const result = response('data: '+ 'x'.repeat(1024*1024+1), 16384);
 await assert.rejects(streamQuestion(result,()=>{},()=>{}), /事件过大/); assert.equal(result.body.locked,false);
});
