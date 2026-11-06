from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from vogue_npp.domain.retrieval import (
    EmptyKnowledgeRetriever, InMemoryMerchDataRepository, InventoryMetric,
    SalesInventoryQuery, SalesMetric, UnconfiguredMerchDataRepository,
)


class RetrievalPortTests(unittest.TestCase):
    def test_unconfigured_adapters_are_explicit(self):
        self.assertEqual(EmptyKnowledgeRetriever().retrieve(None).status, "no_results")
        result = UnconfiguredMerchDataRepository().query_sales_inventory(None)
        self.assertEqual(result.status, "error")
        self.assertIn("not configured", result.limitations[0])

    def test_filters_product_period_channel_and_inventory_as_of(self):
        sales = (
            SalesMetric("P1:S1", 3, 120, "USD", date(2026, 1, 1), date(2026, 1, 31), "web", "fixture"),
            SalesMetric("P1:S1", 8, 300, "USD", date(2026, 1, 1), date(2026, 1, 31), "store", "fixture"),
            SalesMetric("P2:S2", 9, 90, "USD", date(2026, 1, 1), date(2026, 1, 31), "web", "fixture"),
        )
        inventory = (
            InventoryMetric("P1:S1", 0, 0, "units", datetime(2026, 1, 31, tzinfo=timezone.utc), "A", "available", "fixture"),
            InventoryMetric("P1:S1", 4, 0, "units", datetime(2026, 2, 28, tzinfo=timezone.utc), "A", "available", "fixture"),
        )
        repo = InMemoryMerchDataRepository(sales, inventory)
        result = repo.query_sales_inventory(SalesInventoryQuery(
            ("P1",), date(2026, 1, 1), date(2026, 1, 31), "web", datetime(2026, 2, 1, tzinfo=timezone.utc)))
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.sales), 1)
        self.assertEqual(result.sales[0].units_sold, 3)
        self.assertEqual(len(result.inventory), 1)
        self.assertEqual(result.inventory[0].available, 0)

    def test_empty_rows_are_no_results_and_query_failure_is_error(self):
        query = SalesInventoryQuery(("P1",), date(2026, 1, 1), date(2026, 2, 1), None, None)
        self.assertEqual(InMemoryMerchDataRepository().query_sales_inventory(query).status, "no_results")
        self.assertEqual(InMemoryMerchDataRepository(query_status="error").query_sales_inventory(query).status, "error")


if __name__ == "__main__":
    unittest.main()
