import { test } from 'node:test';
import assert from 'node:assert/strict';
import { questionRequestBody, retryQuestionArgs } from '../src/lib/question-request.ts';

const answer = { question: 'When does it open?', knowledge_base_id: 'base-original' };
const catalog = { enabled: true, models: [{ id: 'custom-model' }] };

test('retry preserves the original custom model in the API body', () => {
  const [question, base, modelId] = retryQuestionArgs({ ...answer, requestedModelId: 'custom-model' }, catalog);
  assert.equal(base, 'base-original');
  assert.deepEqual(questionRequestBody(question, modelId), {
    question: answer.question, llm_model_id: 'custom-model',
  });
});

test('retry of an explicit default ask omits llm_model_id even if the catalog is unavailable', () => {
  const [question, , modelId] = retryQuestionArgs({ ...answer, requestedModelId: '' }, null);
  assert.equal(modelId, undefined);
  assert.deepEqual(questionRequestBody(question, modelId), { question: answer.question });
});

test('deleted, disabled, loading or failed model catalogs block a custom retry', () => {
  for (const [available, error] of [[{ enabled: true, models: [] }, false],
    [{ ...catalog, enabled: false }, false], [null, false], [catalog, true]]) {
    assert.throws(() => retryQuestionArgs({ ...answer, requestedModelId: 'custom-model' }, available, error), /已删除或不可用/);
  }
});

test('stored questions with unknown original model cannot silently retry with the default', () => {
  assert.throws(() => retryQuestionArgs(answer, catalog), /无法确认原问答使用的模型/);
});
