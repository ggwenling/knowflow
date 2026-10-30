import copy
import json
import unittest
from pathlib import Path

from contracts.index_batch_hash import batch_sha256


class IndexBatchHashTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = json.loads(Path(__file__).with_name('examples').joinpath(
            'protocol-cases.json').read_text(encoding='utf-8'))
        cls.batch = next(case['payload'] for case in cases if case['name'] == 'index-batch')

    def test_shared_contract_vector_matches_its_digest(self):
        self.assertEqual(
            '0564303225ea440820c2aa05bd93ff31043e7ed80ee36965b16118dc037751bc',
            batch_sha256(self.batch),
        )

    def test_execution_identity_is_part_of_the_digest(self):
        changed = copy.deepcopy(self.batch)
        changed['lease']['fencing'] += 1
        self.assertNotEqual(batch_sha256(self.batch), batch_sha256(changed))

    def test_request_id_and_execution_token_are_not_digest_inputs(self):
        changed = copy.deepcopy(self.batch)
        changed['request_id'] = 'request-replay-with-new-correlation-id'
        changed['lease']['execution_token'] = 'different-secret-value-that-is-not-logged'
        self.assertEqual(batch_sha256(self.batch), batch_sha256(changed))

    def test_digest_rejects_content_hash_mismatch(self):
        changed = copy.deepcopy(self.batch)
        changed['chunks'][0]['text'] += ' altered'
        with self.assertRaisesRegex(ValueError, 'does not match'):
            batch_sha256(changed)

    def test_digest_rejects_non_finite_embedding(self):
        changed = copy.deepcopy(self.batch)
        changed['chunks'][0]['embedding'][0] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'):
            batch_sha256(changed)


if __name__ == '__main__':
    unittest.main()
