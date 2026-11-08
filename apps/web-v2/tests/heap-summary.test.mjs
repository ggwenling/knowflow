import { test } from 'node:test';
import assert from 'node:assert/strict';
import { summarizeHeap } from '../scripts/performance/heap-summary.mjs';

function fixture(adjacency) {
  const strings = ['', 'edge', ...adjacency.map((_, index) => `node-${index}`)];
  const nodes = [], edges = [];
  adjacency.forEach((successors, index) => {
    nodes.push(index === 0 ? 0 : 1, index + 2, index * 2 + 1, index === 0 ? 0 : index * 4, successors.length);
    for (const { to, weak = false } of successors) edges.push(weak ? 1 : 0, 1, to * 5);
  });
  return { snapshot: { meta: { node_fields: ['type', 'name', 'id', 'self_size', 'edge_count'], node_types: [['synthetic', 'object']], edge_fields: ['type', 'name_or_index', 'to_node'], edge_types: [['property', 'weak']] } }, nodes, edges, strings };
}

function reachable(adjacency, removed = -1) {
  const found = new Set([0]), stack = [0];
  while (stack.length) for (const { to, weak } of adjacency[stack.pop()]) if (!weak && to !== removed && !found.has(to)) { found.add(to); stack.push(to); }
  return found;
}

test('heap dominators handle cycles, diamonds, weak edges and unreachable nodes', () => {
  const adjacency = [[{ to: 1 }, { to: 2 }, { to: 5, weak: true }], [{ to: 3 }], [{ to: 3 }], [{ to: 4 }], [{ to: 3 }], []];
  const summary = summarizeHeap(fixture(adjacency)).summary;
  const ranked = new Map(summary.topDominators.map(item => [item.index, item]));
  assert.equal(summary.reachableNodes, 5);
  assert.equal(ranked.get(1).retainedBytes, 4);
  assert.equal(ranked.get(2).retainedBytes, 8);
  assert.equal(ranked.get(3).retainedBytes, 28);
  assert.deepEqual(ranked.get(4).dominators.map(item => item.index), [0, 3, 4]);
  assert.equal(ranked.has(5), false);
});

test('dominator retained sizes match independent reachability removal oracle', () => {
  let seed = 417;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 2 ** 32; };
  for (let run = 0; run < 60; run++) {
    const adjacency = Array.from({ length: 12 }, () => []);
    adjacency.forEach(successors => { for (let to = 1; to < adjacency.length; to++) if (random() < .18) successors.push({ to, weak: random() < .15 }); });
    const summary = summarizeHeap(fixture(adjacency)).summary;
    const ranked = new Map(summary.topDominators.map(item => [item.index, item]));
    const before = reachable(adjacency);
    assert.equal(summary.reachableNodes, before.size);
    for (const node of before) if (node !== 0) {
      const after = reachable(adjacency, node);
      const retained = [...before].filter(index => !after.has(index)).reduce((sum, index) => sum + index * 4, 0);
      assert.equal(ranked.get(node).retainedBytes, retained, `graph ${run}, node ${node}`);
    }
  }
});

test('same-session ids distinguish surviving objects from replacement objects', () => {
  const heap = fixture([[{ to: 1 }], []]);
  const first = summarizeHeap(heap);
  const second = summarizeHeap(heap, first.ids);
  assert.equal(second.groups.get('object:node-1').newCount, 0);
  heap.nodes[5 + 2] = 101;
  assert.equal(summarizeHeap(heap, first.ids).groups.get('object:node-1').newCount, 1);
});
