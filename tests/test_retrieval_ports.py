from __future__ import annotations

import unittest
from vogue_npp.domain.retrieval import EmptyKnowledgeRetriever, RetrievalQuery

class RetrievalPortTests(unittest.TestCase):
    def test_unconfigured_knowledge_retriever_is_explicit(self):
        self.assertEqual(
            EmptyKnowledgeRetriever().retrieve(RetrievalQuery(allowed_source_ids=("test-source",))).status,
            "not_configured",
        )

    def test_every_query_requires_source_allowlist_and_evidence_lookup_ids(self):
        with self.assertRaisesRegex(ValueError, "source allowlist"):
            RetrievalQuery()
        with self.assertRaisesRegex(ValueError, "evidence_ids"):
            RetrievalQuery(purpose="evidence_lookup", allowed_source_ids=("test-source",))

if __name__ == "__main__":
    unittest.main()
