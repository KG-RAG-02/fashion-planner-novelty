from __future__ import annotations

import unittest
from vogue_npp.domain.retrieval import EmptyKnowledgeRetriever

class RetrievalPortTests(unittest.TestCase):
    def test_unconfigured_knowledge_retriever_is_explicit(self):
        self.assertEqual(EmptyKnowledgeRetriever().retrieve(None).status, "no_results")

if __name__ == "__main__":
    unittest.main()
