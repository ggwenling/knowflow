import { execFileSync } from 'node:child_process';
import { mkdir, writeFile, readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const root=resolve(import.meta.dirname,'../..');
const images={baseline:'knowflow-web-v2-baseline:optimization',optimized:'knowflow-web-v2-optimized:local'};
const docker=(args,options={})=>execFileSync('docker',args,{cwd:root,encoding:'utf8',...options});
const hash=createHash('sha256');
async function fingerprint(directory){for(const file of (await readdir(directory,{withFileTypes:true})).toSorted((a,b)=>a.name.localeCompare(b.name))){const path=resolve(directory,file.name);if(file.isDirectory())await fingerprint(path);else{hash.update(path.slice(root.length));hash.update(await readFile(path));}}}
await fingerprint(resolve(root,'src'));hash.update(await readFile(resolve(root,'package-lock.json')));
const sourceDigest=hash.digest('hex');
if(!process.argv.includes('--skip-build')){
 docker(['build','-t',images.baseline,'-f','scripts/performance/Dockerfile.baseline','.'],{stdio:'inherit'});
 docker(['build','-t',images.optimized,'.'],{stdio:'inherit'});
}
const containers=[];const rows=[];
try{
 for(const [mode,image]of Object.entries(images)){
  const name=`knowflow-perf-${mode}-${process.pid}`;
  docker(['run','--detach','--name',name,'--publish','127.0.0.1::3000',image]);containers.push(name);
  const ports=JSON.parse(docker(['inspect','--format','{{json .NetworkSettings.Ports}}',name]));
  const url='http://127.0.0.1:'+ports['3000/tcp'][0].HostPort;
  const deadline=Date.now()+30_000;let ready=false;
  while(Date.now()<deadline){try{if((await fetch(url+'/api/mode',{signal:AbortSignal.timeout(1000)})).ok){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,200));}
  if(!ready)throw new Error(mode+' container did not become ready');
  for(let i=0;i<20;i++){const response=await fetch(url+'/login');if(!response.ok)throw new Error('Login failed');await response.arrayBuffer();}
  const probe=String.raw`const fs=require("node:fs");let rss=0,count=0;for(const id of fs.readdirSync("/proc")){if(!/^\d+$/.test(id)||Number(id)===process.pid)continue;try{const cmd=fs.readFileSync("/proc/"+id+"/cmdline","utf8");if(cmd.startsWith("next-server")){const status=fs.readFileSync("/proc/"+id+"/status","utf8");rss+=Number(status.match(/VmRSS:\s+(\d+)/)[1])*1024;count++;}}catch{}}if(!count)process.exit(2);console.log(JSON.stringify({rss,processes:count}));`;
  const samples=[];for(let i=0;i<3;i++){samples.push(JSON.parse(docker(['exec',name,'node','-e',probe])));await new Promise(resolve=>setTimeout(resolve,200));}
  const rss=samples.map(item=>item.rss).toSorted((a,b)=>a-b)[1];
  const size=Number(docker(['image','inspect',image,'--format','{{.Size}}']).trim());
  rows.push({mode,image,imageBytes:size,serverRssBytes:rss,rssSamples:samples});
 }
 const report={generatedAt:new Date().toISOString(),sourceDigest,conditions:'Same working-tree source and pinned Node image; baseline removes standalone output and uses legacy full production dependencies; 20 localhost login GETs; 3 /proc VmRSS samples of the actual next-server process; no backend configured',rows};
 const output=resolve(root,'performance-results/containers.json');await mkdir(resolve(output,'..'),{recursive:true});await writeFile(output,JSON.stringify(report,null,2)+'\n');console.table(rows.map(({mode,imageBytes,serverRssBytes})=>({mode,imageBytes,serverRssBytes})));console.log('Report: '+output);
}finally{for(const name of containers)docker(['rm','--force',name],{stdio:'ignore'});}
