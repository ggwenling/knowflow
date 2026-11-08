import { spawnSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { readBoundedBody } from '../../src/lib/bounded-body.ts';
import { sliceCodePoints } from '../../src/lib/text-range.ts';

const mode = process.argv.find(arg => arg.startsWith('--case='))?.slice(7);
if (mode) {
 if (!global.gc) throw new Error('Run with --expose-gc');
 global.gc(); const before = process.memoryUsage(); let peak = {...before};
 const sample = () => { const next=process.memoryUsage(); for(const key of Object.keys(next)) peak[key]=Math.max(peak[key],next[key]); };
 const start=performance.now();
 if(mode.startsWith('upload-')) {
  let offset=0; const limit=8*1024*1024;
  const source=new ReadableStream({pull(controller) {
   if(offset===limit){controller.close();return;}
   const chunk=new Uint8Array(Math.min(65536,limit-offset)); chunk.fill(97); offset+=chunk.length; controller.enqueue(chunk);
   if(offset%(1024*1024)===0)global.gc(); sample();
  }});
  let result;
  if(mode==='upload-baseline'){
   const reader=source.getReader(); const chunks=[]; let length=0;
   while(true){const next=await reader.read();if(next.done)break;chunks.push(next.value);length+=next.value.length;}
   result=new Uint8Array(length);let at=0;for(const chunk of chunks){result.set(chunk,at);at+=chunk.length;}sample();
   if(chunks.length!==128)throw new Error('Invalid fixture');
  } else result=await readBoundedBody(source,new AbortController().signal,9*1024*1024,limit);
  sample();if(result.length!==limit||result[limit-1]!==97)throw new Error('Incorrect body');
 } else {
  const text='中文😀'.repeat(250000); let result;
  if(mode==='text-baseline'){const expanded=Array.from(text);result=expanded.slice(200000,200100).join('');sample();if(!expanded.length)throw new Error('Invalid fixture');}
  else result=sliceCodePoints(text,200000,200100);
  sample();if(Array.from(result).length!==100)throw new Error('Incorrect excerpt');
 }
 console.log(JSON.stringify({mode,durationMs:performance.now()-start,peakRssDelta:Math.max(0,peak.rss-before.rss),peakHeapDelta:Math.max(0,peak.heapUsed-before.heapUsed),peakArrayBuffersDelta:Math.max(0,peak.arrayBuffers-before.arrayBuffers)}));
} else {
 const samples=[];
 for(const name of ['upload-baseline','upload-optimized','text-baseline','text-optimized'])for(let run=0;run<3;run++){
  const child=spawnSync(process.execPath,['--expose-gc',import.meta.filename,'--case='+name],{encoding:'utf8'});
  if(child.status!==0)throw new Error(child.stderr||'Memory sample failed');
  samples.push(JSON.parse(child.stdout));
 }
 const median=values=>values.toSorted((a,b)=>a-b)[Math.floor(values.length/2)];
 const summary=[...new Set(samples.map(item=>item.mode))].map(mode=>{const rows=samples.filter(item=>item.mode===mode);return {mode,peakRssDelta:median(rows.map(x=>x.peakRssDelta)),peakHeapDelta:median(rows.map(x=>x.peakHeapDelta)),peakArrayBuffersDelta:median(rows.map(x=>x.peakArrayBuffersDelta))};});
 const report={node:process.version,fixture:'8 MiB / 64 KiB chunks; 750000 code-point text; 3 isolated processes per case',conditions:'GC stress benchmark, not production latency; sampled RSS includes allocator noise; resizable buffers may not appear in arrayBuffers',samples,summary};
 const output=resolve(import.meta.dirname,'../../performance-results/memory.json');await mkdir(resolve(output,'..'),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');console.table(summary);console.log('Report: '+output);
}
