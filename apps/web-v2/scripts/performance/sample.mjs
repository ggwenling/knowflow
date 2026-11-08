import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const baseUrl=process.env.KNOWFLOW_E2E_BASE_URL ?? 'http://127.0.0.1:3300';
const output=resolve(import.meta.dirname,'../../performance-results');
const cpu=Number(process.env.PERF_CPU_RATE ?? 1);
const repeats=Number(process.env.PERF_REPEATS ?? 3);
if(!Number.isFinite(cpu)||cpu<1||!Number.isInteger(repeats)||repeats<1||repeats>10)throw new Error('Invalid sample settings');
await mkdir(output,{recursive:true});
const browser=await chromium.launch(); const samples=[];
try {
 for(const path of ['/','/conversations','/settings','/login']) for(let run=0;run<repeats;run++){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(()=>{
   window.__perf={lcp:0,cls:0,longTasks:[],metrics:[]};
   new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__perf.lcp=entry.startTime;}).observe({type:'largest-contentful-paint',buffered:true});
   let sessionStart=0;let lastShift=0;let sessionValue=0;
   new PerformanceObserver(list=>{for(const entry of list.getEntries()){
    if(entry.hadRecentInput)continue;
    if(entry.startTime-lastShift<1000&&entry.startTime-sessionStart<5000)sessionValue+=entry.value;
    else {sessionStart=entry.startTime;sessionValue=entry.value;}
    lastShift=entry.startTime;window.__perf.cls=Math.max(window.__perf.cls,sessionValue);
   }}).observe({type:'layout-shift',buffered:true});
   new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__perf.longTasks.push(entry.duration);}).observe({type:'longtask',buffered:true});
   window.addEventListener('knowflow-performance',event=>window.__perf.metrics.push(event.detail));
  });
  const page=await context.newPage(); const cdp=await context.newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:cpu});await cdp.send('Performance.enable');
  let apiRequests=0;
  await page.route('**/api/**',async route=>{
   apiRequests++;const p=new URL(route.request().url()).pathname;
   if(p==='/api/mode')return route.fulfill({json:{mode:'synthetic'}});
   if(p==='/api/v1/me')return path==='/login'?route.fulfill({status:401,json:{code:'UNAUTHENTICATED'}}):route.fulfill({json:{user_id:'perf-user',email:'perf@example.test'}});
   if(p==='/api/v1/knowledge-bases')return route.fulfill({json:{items:[{id:'perf-base',name:'性能验收资料库',status:'ACTIVE'}],has_more:false}});
   if(p==='/api/v1/questions')return route.fulfill({json:{items:Array.from({length:50},(_,i)=>({question_id:'q-'+i,knowledge_base_id:'perf-base',question:'性能验收问题 '+i,status:'SUCCEEDED',finished_at:'2026-11-07T12:00:00Z'})),has_more:false}});
   if(p.endsWith('/documents'))return route.fulfill({json:{items:Array.from({length:50},(_,i)=>({id:'doc-'+i,original_name:'性能资料 '+i+'.txt',format:'txt',byte_size:1024,status:'READY',active_index_version_id:'idx-'+i})),has_more:false}});
   return route.fulfill({status:404,json:{code:'NOT_FOUND'}});
  });
  const tracing=path==='/'&&run===0;
  if(tracing)await cdp.send('Tracing.start',{categories:'devtools.timeline,v8.execute,blink.user_timing',transferMode:'ReturnAsStream'});
  await page.goto(new URL(path,baseUrl).href);await page.locator('h1').first().waitFor();
  if(path==='/')await page.locator('button[aria-label="提问"][title="发送问题"]').waitFor();
  if(path==='/conversations')await page.locator('#desk-question').waitFor({state:'visible'});
  const shellReadyMs=await page.evaluate(()=>performance.now());
  if(path==='/'||path==='/login')await page.locator('canvas').waitFor({state:'visible'});
  await page.evaluate(async()=>{await document.fonts.ready;await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
  const data=await page.evaluate(()=>({
   ...window.__perf,
   measuredAtMs:performance.now(),
   navigation:performance.getEntriesByType('navigation').map(e=>({ttfb:e.responseStart,domContentLoaded:e.domContentLoadedEventEnd,load:e.loadEventEnd})),
   resources:performance.getEntriesByType('resource').map(e=>({url:new URL(e.name).pathname,decoded:e.decodedBodySize,transfer:e.transferSize,initiator:e.initiatorType,start:e.startTime,duration:e.duration})),
   preloadedFonts:[...document.querySelectorAll('link[rel=preload][as=font]')].map(e=>new URL(e.href).pathname),
   canvas:!!document.querySelector('canvas')
  }));
  const metrics=Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(item=>[item.name,item.value]));
  samples.push({path,run,shellReadyMs,apiRequests,...data,cdp:{JSHeapUsedSize:metrics.JSHeapUsedSize,LayoutCount:metrics.LayoutCount,TaskDuration:metrics.TaskDuration,ScriptDuration:metrics.ScriptDuration}});
  if(run===0){
   await page.waitForFunction(()=>{const element=document.querySelector('main#main-content > div')??document.querySelector('main > section');return !element||Number(getComputedStyle(element).opacity)>=.999;});
   await page.screenshot({path:resolve(output,(path==='/'?'home':path.slice(1))+'-1440.png'),fullPage:true});
   if(path==='/'){await page.setViewportSize({width:390,height:844});await page.screenshot({path:resolve(output,'home-390.png'),fullPage:true});}
  }
  if(tracing){
   const complete=new Promise(resolve=>cdp.once('Tracing.tracingComplete',resolve));await cdp.send('Tracing.end');const {stream}=await complete;const parts=[];
   while(true){const result=await cdp.send('IO.read',{handle:stream});parts.push(Buffer.from(result.data,result.base64Encoded?'base64':'utf8'));if(result.eof)break;}
   await cdp.send('IO.close',{handle:stream});await writeFile(resolve(output,'home-trace.json'),Buffer.concat(parts));
  }
  await context.close();
 }
 const retentionContext=await browser.newContext({viewport:{width:1440,height:1000}});
 const retentionPage=await retentionContext.newPage();
 await retentionPage.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/mode')return route.fulfill({json:{mode:'synthetic'}});
  if(path==='/api/v1/me')return route.fulfill({json:{user_id:'retention',email:'retention@example.test'}});
  if(path==='/api/v1/knowledge-bases')return route.fulfill({json:{items:[{id:'base',name:'资源释放验收',status:'ACTIVE'}],has_more:false}});
  return route.fulfill({json:{items:[],has_more:false}});
 });
 const retentionCdp=await retentionContext.newCDPSession(retentionPage);await retentionCdp.send('Performance.enable');
 await retentionPage.goto(new URL('/workflow',baseUrl).href);
 const cycle=async()=>{
  const navigation=retentionPage.getByRole('navigation',{name:'主导航'});
  await navigation.getByRole('link',{name:'首页',exact:true}).click();await retentionPage.locator('canvas').waitFor({state:'visible'});
  await navigation.getByRole('link',{name:'工作流',exact:true}).click();await retentionPage.locator('canvas').waitFor({state:'detached'});
 };
 await cycle();await cycle();
 const retained=async()=>{
  await retentionCdp.send('HeapProfiler.collectGarbage');
  const values=Object.fromEntries((await retentionCdp.send('Performance.getMetrics')).metrics.map(item=>[item.name,item.value]));
  return {heapBytes:values.JSHeapUsedSize,...await retentionCdp.send('Memory.getDOMCounters')};
 };
 const retentionBefore=await retained();
 for(let i=0;i<20;i++)await cycle();
 const retentionAfter=await retained();
 const retentionSamples=[{cycles:0,...retentionBefore},{cycles:20,...retentionAfter}];
 for(const cycles of [40,60]){for(let i=0;i<20;i++)await cycle();retentionSamples.push({cycles,...await retained()});}
 await writeFile(resolve(output,'retention.json'),JSON.stringify({conditions:'SPA home/workflow navigation, 2 warmup and 60 measured round trips in 20-cycle batches; each home awaits live WebGL, each exit awaits canvas removal; Chromium GC before snapshots; measures retained JS/DOM, not GPU memory',before:retentionBefore,after:retentionSamples.at(-1),samples:retentionSamples},null,2)+'\n');
 await retentionContext.close();
 const report={generatedAt:new Date().toISOString(),browser:browser.version(),node:process.version,conditions:{mode:'production server, mocked API',cpuRate:cpu,network:'local, no network throttling',cache:'fresh context per sample',viewport:'1440x1000',repeats},samples};
 await writeFile(resolve(output,'browser.json'),JSON.stringify(report,null,2)+'\n');
 console.table(samples.map(item=>({route:item.path,run:item.run,shellReady:Math.round(item.shellReadyMs),lcp:Math.round(item.lcp),cls:item.cls,jsDecoded:item.resources.filter(e=>e.url.endsWith('.js')).reduce((sum,e)=>sum+e.decoded,0),heap:item.cdp.JSHeapUsedSize,apiRequests:item.apiRequests})));
 console.log('Report: '+resolve(output,'browser.json'));
} finally {await browser.close();}
