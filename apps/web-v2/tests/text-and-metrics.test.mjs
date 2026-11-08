import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sliceCodePoints } from '../src/lib/text-range.ts';
import { uploadError, maxUploadBytes } from '../src/lib/upload-rules.ts';
import { metricRoute } from '../src/lib/performance.ts';

test('text locators preserve Unicode code point semantics', () => {
 const value = '中文😀e\u0301𠮷结尾';
 for (let start=0;start<12;start++) for(let end=start;end<14;end++) assert.equal(sliceCodePoints(value,start,end),Array.from(value).slice(start,end).join(''));
 assert.equal(sliceCodePoints(value,-1,3),'');
});
test('all upload entry points use one format and size policy', () => {
 assert.equal(uploadError({name:'资料.PDF',size:maxUploadBytes}),null);
 assert.match(uploadError({name:'资料.pdf',size:maxUploadBytes+1}),/8 MiB/);
 assert.match(uploadError({name:'file.exe',size:1}),/文件格式/);
 assert.match(uploadError({name:'no-extension',size:1}),/文件格式/);
});
test('metrics normalize routes without IDs, query strings or unknown paths', () => {
 assert.equal(metricRoute('/conversations/private-id?question=secret'),'/conversations/[questionId]');
 assert.equal(metricRoute('/knowledge-bases/private-id'),'/knowledge-bases/[baseId]');
 assert.equal(metricRoute('/?email=secret'),'/');
 assert.equal(metricRoute('/private-data/secret'),'/other');
});
