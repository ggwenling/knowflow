import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { gzipSync } from 'node:zlib';

const root = resolve(import.meta.dirname, '../..');
const budgets = JSON.parse(await readFile(resolve(root, 'performance/budgets.json'), 'utf8'));
const stats = JSON.parse(await readFile(resolve(root, '.next/diagnostics/route-bundle-stats.json'), 'utf8'));
if (!Array.isArray(stats) || budgets.schemaVersion !== 1) throw new Error('Unsupported bundle report or budget schema; do not silently skip this gate.');
const cache = new Map();
async function size(path) {
 if (!cache.has(path)) cache.set(path, readFile(resolve(root,path.replaceAll('\\','/'))).then(bytes => ({raw:bytes.length,gzip:gzipSync(bytes,{level:9}).length})));
 return cache.get(path);
}
const routes = [];
for (const [route,baselineGzip] of Object.entries(budgets.routes)) {
 const entry = stats.find(item => item.route === route);
 if (!entry || !Array.isArray(entry.firstLoadChunkPaths)) throw new Error(`Missing build data for ${route}`);
 const sizes = await Promise.all([...new Set(entry.firstLoadChunkPaths)].map(size));
 const gzip = sizes.reduce((sum,item) => sum+item.gzip,0);
 routes.push({route,raw:sizes.reduce((sum,item) => sum+item.raw,0),gzip,baselineGzip,changePercent:Number(((gzip/baselineGzip-1)*100).toFixed(2)),limit:Math.ceil(baselineGzip*budgets.maxGrowthRatio),pass:gzip<=Math.ceil(baselineGzip*budgets.maxGrowthRatio)});
}
const report = {schemaVersion:1,generatedAt:new Date().toISOString(),node:process.version,compression:'sum of unique first-load JS chunks, gzip level 9',baseline:budgets.baseline,routes};
const output = resolve(root, process.env.PERF_BUNDLE_REPORT ?? 'performance-results/bundle.json');
await mkdir(dirname(output),{recursive:true}); await writeFile(output,JSON.stringify(report,null,2)+'\n');
console.table(routes.map(({route,gzip,baselineGzip,changePercent,pass})=>({route,gzip,baselineGzip,changePercent,pass})));
console.log(`Report: ${output}`);
if(routes.some(item=>!item.pass)) process.exitCode=1;
