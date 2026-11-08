import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Diagnostic graph: exclude weak edges; include internal/shortcut edges.
// This is not Chrome DevTools' ephemeron/native retained-size implementation.
// Only process synthetic localhost snapshots, which remain in ignored performance-results.
export function summarizeHeap(heap, baselineIds = new Set()) {
  const { nodes, edges, strings } = heap;
  const meta = heap.snapshot.meta;
  const nf = meta.node_fields.length, ef = meta.edge_fields.length;
  const ni = Object.fromEntries(meta.node_fields.map((name, index) => [name, index]));
  const ei = Object.fromEntries(meta.edge_fields.map((name, index) => [name, index]));
  const types = meta.node_types[ni.type], edgeTypes = meta.edge_types[ei.type];
  const count = nodes.length / nf;
  const starts = new Uint32Array(count + 1);
  for (let i = 0; i < count; i++) starts[i + 1] = starts[i] + nodes[i * nf + ni.edge_count] * ef;
  const target = offset => edges[offset + ei.to_node] / nf;
  const strong = offset => edgeTypes[edges[offset + ei.type]] !== 'weak';
  const name = index => strings[nodes[index * nf + ni.name]];
  const id = index => nodes[index * nf + ni.id];
  const self = index => nodes[index * nf + ni.self_size];
  const type = index => types[nodes[index * nf + ni.type]];
  const description = index => ({ index, id: id(index), type: type(index), name: name(index).slice(0, 180), selfBytes: self(index) });
  const edgeName = offset => {
    const type = edgeTypes[edges[offset + ei.type]];
    const raw = edges[offset + ei.name_or_index];
    return `${type}:${type === 'element' || type === 'hidden' ? raw : strings[raw]}`.slice(0, 200);
  };
  // DFS numbering, parents and postorder. All arrays use DFS numbers except starts/dfs.
  const dfs = new Uint32Array(count);
  const vertex = new Uint32Array(count + 1);
  const parent = new Uint32Array(count + 1);
  dfs[0] = 1; vertex[1] = 0;
  let reached = 1;
  const stack = [0], cursor = [starts[0]];
  while (stack.length) {
    const top = stack.length - 1, node = stack[top];
    if (cursor[top] >= starts[node + 1]) { stack.pop(); cursor.pop(); continue; }
    const offset = cursor[top]; cursor[top] += ef;
    if (!strong(offset)) continue;
    const to = target(offset);
    if (dfs[to]) continue;
    dfs[to] = ++reached; vertex[reached] = to; parent[reached] = dfs[node];
    stack.push(to); cursor.push(starts[to]);
  }
  // Incoming strong edges as linked arrays. Preserve offsets for shortest root paths.
  const heads = new Int32Array(count); heads.fill(-1);
  const edgeCount = edges.length / ef;
  const previous = new Int32Array(edgeCount); previous.fill(-1);
  const sources = new Uint32Array(edgeCount);
  for (let from = 0; from < count; from++) if (dfs[from]) {
    for (let offset = starts[from]; offset < starts[from + 1]; offset += ef) if (strong(offset)) {
      const to = target(offset), e = offset / ef;
      sources[e] = from; previous[e] = heads[to]; heads[to] = e;
    }
  }
  // Lengauer-Tarjan immediate dominators.
  const semi = new Uint32Array(reached + 1), ancestor = new Uint32Array(reached + 1);
  const label = new Uint32Array(reached + 1), dom = new Uint32Array(reached + 1);
  const bucketHead = new Uint32Array(reached + 1), bucketNext = new Uint32Array(reached + 1);
  for (let v = 1; v <= reached; v++) semi[v] = label[v] = v;
  const evaluate = v => {
    if (!ancestor[v]) return label[v];
    const path = [];
    let x = v;
    while (ancestor[ancestor[x]]) { path.push(x); x = ancestor[x]; }
    while (path.length) {
      const y = path.pop(), a = ancestor[y];
      if (semi[label[a]] < semi[label[y]]) label[y] = label[a];
      ancestor[y] = ancestor[a];
    }
    return label[v];
  };
  for (let w = reached; w >= 2; w--) {
    for (let e = heads[vertex[w]]; e !== -1; e = previous[e]) {
      const v = dfs[sources[e]];
      const u = evaluate(v);
      if (semi[u] < semi[w]) semi[w] = semi[u];
    }
    bucketNext[w] = bucketHead[semi[w]]; bucketHead[semi[w]] = w;
    ancestor[w] = parent[w];
    let v = bucketHead[parent[w]];
    bucketHead[parent[w]] = 0;
    while (v) {
      const u = evaluate(v);
      dom[v] = semi[u] < semi[v] ? u : parent[w];
      v = bucketNext[v];
    }
  }
  for (let w = 2; w <= reached; w++) if (dom[w] !== semi[w]) dom[w] = dom[dom[w]];
  const retained = new Float64Array(reached + 1);
  for (let v = 1; v <= reached; v++) retained[v] = self(vertex[v]);
  for (let v = reached; v >= 2; v--) retained[dom[v]] += retained[v];
  // BFS gives one shortest strong root path; not an exhaustive set of retainers.
  const queue = new Uint32Array(reached), pathParent = new Int32Array(count), pathEdge = new Int32Array(count);
  pathParent.fill(-1); pathEdge.fill(-1); pathParent[0] = 0;
  let head = 0, tail = 1; queue[0] = 0;
  while (head < tail) {
    const from = queue[head++];
    for (let offset = starts[from]; offset < starts[from + 1]; offset += ef) if (strong(offset)) {
      const to = target(offset);
      if (pathParent[to] !== -1) continue;
      pathParent[to] = from; pathEdge[to] = offset; queue[tail++] = to;
    }
  }
  const rootPath = node => {
    const result = [];
    let current = node;
    for (let depth = 0; depth < 80; depth++) {
      const offset = pathEdge[current];
      result.push({ ...description(current), via: offset < 0 ? 'root' : edgeName(offset) });
      if (current === 0 || pathParent[current] < 0) break;
      current = pathParent[current];
    }
    return result.reverse();
  };
  const domPath = node => {
    const result = [];
    let v = dfs[node];
    while (v) { result.push({ ...description(vertex[v]), retainedBytes: retained[v] }); v = dom[v]; }
    return result.reverse();
  };
  const groups = new Map(), ids = new Set(), typeTotals = new Map();
  const census = { reactFibers: 0, threeRenderers: 0, detachedNodes: 0 };
  for (let node = 0; node < count; node++) {
    let total = typeTotals.get(type(node));
    if (!total) typeTotals.set(type(node), total = { type: type(node), count: 0, selfBytes: 0 });
    total.count++; total.selfBytes += self(node);
    if (ni.detachedness !== undefined && nodes[node * nf + ni.detachedness] === 2) census.detachedNodes++;
    if (type(node) === 'object') {
      const properties = new Set();
      for (let offset = starts[node]; offset < starts[node + 1]; offset += ef) if (edgeTypes[edges[offset + ei.type]] === 'property') properties.add(strings[edges[offset + ei.name_or_index]]);
      if (['tag', 'return', 'child', 'alternate'].every(key => properties.has(key))) census.reactFibers++;
      if (['domElement', 'render', 'dispose', 'getContext'].every(key => properties.has(key))) census.threeRenderers++;
    }
    ids.add(id(node));
    const key = `${type(node)}:${name(node)}`;
    let group = groups.get(key);
    if (!group) groups.set(key, group = { type: type(node), name: name(node).slice(0, 180), count: 0, selfBytes: 0, newCount: 0, newSelfBytes: 0, reachableCount: 0 });
    group.count++; group.selfBytes += self(node); if (dfs[node]) group.reachableCount++;
    if (!baselineIds.has(id(node))) { group.newCount++; group.newSelfBytes += self(node); }
  }
  const ranked = Array.from({ length: count }, (_, index) => index).filter(index => dfs[index] && index !== 0 && !['synthetic'].includes(type(index))).sort((a, b) => retained[dfs[b]] - retained[dfs[a]]);
  const detail = node => ({ ...description(node), retainedBytes: retained[dfs[node]], existedAtBaseline: baselineIds.has(id(node)), dominators: domPath(node), shortestStrongPath: rootPath(node) });
  const selectedNames = /^(WebGLRenderer|WebGLRenderingContext|WebGL2RenderingContext|HTMLCanvasElement|ResizeObserver|IntersectionObserver|AbortController|AbortSignal|PerformanceResourceTiming|PerformanceMeasure|PerformanceMark|Detached.*|FiberNode|Map|Set|Promise)$/;
  const selectedGroups = [...groups.values()].filter(group => selectedNames.test(group.name));
  const selectedObjects = ranked.filter(index => selectedNames.test(name(index))).slice(0, 35).map(detail);
  const diagnosticNames = new Set(['system / InstructionStream', 'system / Code', 'system / TrustedByteArray', 'system / FeedbackVector', 'PerformanceResourceTiming', 'LayoutShift', 'LargestContentfulPaint', 'blink::NetworkResourcesData::ResourceData']);
  const diagnosticExamples = [];
  for (const targetName of diagnosticNames) {
    const candidates = ranked.filter(index => name(index) === targetName);
    const example = candidates.find(index => !baselineIds.has(id(index))) ?? candidates[0];
    if (example !== undefined) diagnosticExamples.push(detail(example));
  }
  return {
    ids, groups,
    summary: { nodes: count, reachableNodes: reached, strongGraphSelfBytes: retained[1], typeTotals: [...typeTotals.values()], census, diagnosticExamples, topGroupsBySelf: [...groups.values()].sort((a, b) => b.selfBytes - a.selfBytes).slice(0, 45), selectedGroups, topDominators: ranked.slice(0, 25).map(detail), topNewDominators: ranked.filter(index => !baselineIds.has(id(index))).slice(0, 25).map(detail), selectedObjects },
  };
}

if (process.argv[1] && resolve(process.argv[1]) === import.meta.filename) {
  const files = process.argv.slice(2);
  if (!files.length) throw new Error('Usage: node heap-summary.mjs baseline.heapsnapshot middle.heapsnapshot end.heapsnapshot');
  let baselineIds, baselineGroups;
  const reports = [];
  for (const file of files) {
    const result = summarizeHeap(JSON.parse(await readFile(file, 'utf8')), baselineIds);
    const growth = [...result.groups].map(([key, group]) => {
      const before = baselineGroups?.get(key);
      return { ...group, countDelta: group.count - (before?.count ?? 0), selfBytesDelta: group.selfBytes - (before?.selfBytes ?? 0) };
    }).filter(group => group.countDelta !== 0 || group.selfBytesDelta !== 0).sort((a, b) => b.selfBytesDelta - a.selfBytesDelta);
    const entry = { file, ...result.summary, growthBySelf: baselineGroups ? growth.slice(0, 60) : [], countGrowth: baselineGroups ? [...growth].sort((a, b) => b.countDelta - a.countDelta).slice(0, 40) : [] };
    await writeFile(file + '.summary.json', JSON.stringify(entry, null, 2) + '\n');
    reports.push({ file, nodes: entry.nodes, reachableNodes: entry.reachableNodes, strongGraphSelfBytes: entry.strongGraphSelfBytes, growthBySelf: entry.growthBySelf.slice(0, 15), selectedGroups: entry.selectedGroups });
    baselineIds ??= result.ids; baselineGroups ??= result.groups;
    console.log(`${file}: ${entry.nodes} nodes; ${entry.strongGraphSelfBytes} reachable self bytes`);
  }
  await writeFile(files.at(-1) + '.comparison.json', JSON.stringify({ caveat: 'Strong-edge diagnostic graph excluding weak edges; shortest root path is one path, dominators not Chrome ephemeron/native retained-size semantics. Same-session V8 ids used for baseline survival.', reports }, null, 2) + '\n');
}
