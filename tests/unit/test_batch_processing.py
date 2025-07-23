"""Tests for batch processing utilities."""

from __future__ import annotations

import asyncio
from typing import Any

from meraki_dashboard_exporter.core.batch_processing import (
    extract_successful_results,
    process_grouped_items,
    process_in_batches_with_errors,
)


class TestProcessInBatchesWithErrors:
    """Test process_in_batches_with_errors functionality."""

    async def test_successful_batch_processing(self):
        """Test processing items successfully in batches."""
        processed_items = []

        async def process_item(item: int) -> str:
            await asyncio.sleep(0.01)
            processed_items.append(item)
            return f"processed_{item}"

        items = list(range(10))
        results = await process_in_batches_with_errors(
            items, process_item, batch_size=3, delay_between_batches=0.05, item_description="number"
        )

        # All items should be processed
        assert len(results) == 10
        assert sorted(processed_items) == items

        # Check results
        for i, (item, result) in enumerate(results):
            assert item == i
            assert result == f"processed_{i}"

    async def test_batch_processing_with_errors(self):
        """Test handling errors during batch processing."""

        async def process_item(item: int) -> str:
            await asyncio.sleep(0.01)
            if item % 3 == 0:
                raise ValueError(f"Item {item} failed")
            return f"processed_{item}"

        items = list(range(9))
        results = await process_in_batches_with_errors(
            items, process_item, batch_size=3, item_description="number"
        )

        # All items should have results (either success or exception)
        assert len(results) == 9

        # Check successful and failed items
        successful = 0
        failed = 0
        for item, result in results:
            if isinstance(result, Exception):
                failed += 1
                assert item % 3 == 0
                assert str(result) == f"Item {item} failed"
            else:
                successful += 1
                assert result == f"processed_{item}"

        assert successful == 6  # items 1,2,4,5,7,8
        assert failed == 3  # items 0,3,6

    async def test_batch_size_respected(self):
        """Test that batch size limits concurrency."""
        concurrent_count = 0
        max_concurrent = 0

        async def process_item(item: int) -> int:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return item

        items = list(range(10))
        await process_in_batches_with_errors(
            items, process_item, batch_size=3, delay_between_batches=0
        )

        # Max concurrent should not exceed batch size
        assert max_concurrent <= 3

    async def test_delay_between_batches(self):
        """Test delay between batch processing."""
        batch_times = []

        async def process_item(item: int) -> int:
            batch_times.append((item, asyncio.get_event_loop().time()))
            return item

        items = list(range(6))
        await process_in_batches_with_errors(
            items, process_item, batch_size=2, delay_between_batches=0.1
        )

        # Should have 3 batches: [0,1], [2,3], [4,5]
        # Check delays between batches
        batch1_end = max(t for i, t in batch_times if i in {0, 1})
        batch2_start = min(t for i, t in batch_times if i in {2, 3})
        batch2_end = max(t for i, t in batch_times if i in {2, 3})
        batch3_start = min(t for i, t in batch_times if i in {4, 5})

        assert batch2_start - batch1_end >= 0.09  # Allow small variance
        assert batch3_start - batch2_end >= 0.09

    async def test_error_context_function(self):
        """Test custom error context extraction."""
        # Track error contexts to ensure they are properly used

        async def process_item(item: dict[str, Any]) -> str:
            if item["fail"]:
                raise ValueError(f"Failed processing {item['id']}")
            return f"processed_{item['id']}"

        def get_error_context(item: dict[str, Any]) -> dict[str, Any]:
            return {"item_id": item["id"], "item_type": item["type"]}

        items = [
            {"id": 1, "type": "A", "fail": False},
            {"id": 2, "type": "B", "fail": True},
            {"id": 3, "type": "A", "fail": False},
        ]

        # Capture log output to verify context was used
        results = await process_in_batches_with_errors(
            items, process_item, error_context_func=get_error_context, item_description="test_item"
        )

        # Check results
        assert len(results) == 3
        assert results[0][1] == "processed_1"
        assert isinstance(results[1][1], ValueError)
        assert results[2][1] == "processed_3"

    async def test_empty_items_list(self):
        """Test processing empty list."""

        async def process_item(item: int) -> str:
            return f"processed_{item}"

        results = await process_in_batches_with_errors([], process_item, batch_size=3)

        assert results == []

    async def test_single_item(self):
        """Test processing single item."""

        async def process_item(item: str) -> str:
            return f"processed_{item}"

        results = await process_in_batches_with_errors(["test"], process_item, batch_size=10)

        assert len(results) == 1
        assert results[0] == ("test", "processed_test")

    async def test_base_exception_filtering(self):
        """Test that non-Exception BaseExceptions are filtered out."""

        # Create custom BaseException for testing
        class CustomBaseException(BaseException):
            pass

        async def process_item(item: int) -> str:
            if item == 1:
                raise CustomBaseException("Not an Exception")  # BaseException but not Exception
            elif item == 2:
                raise ValueError("Regular exception")
            return f"processed_{item}"

        items = [0, 1, 2, 3]
        results = await process_in_batches_with_errors(items, process_item, batch_size=4)

        # CustomBaseException should be filtered out
        assert len(results) == 3
        assert results[0] == (0, "processed_0")
        # Item 1 with CustomBaseException is filtered out
        assert results[1][0] == 2
        assert isinstance(results[1][1], ValueError)
        assert results[2] == (3, "processed_3")


class TestProcessGroupedItems:
    """Test process_grouped_items functionality."""

    async def test_grouped_processing(self):
        """Test processing items grouped by key."""

        async def process_item(item: str) -> str:
            await asyncio.sleep(0.01)
            return f"processed_{item}"

        items_by_group = {
            "group_a": ["a1", "a2", "a3"],
            "group_b": ["b1", "b2"],
            "group_c": ["c1"],
        }

        results = await process_grouped_items(
            items_by_group,
            process_item,
            batch_size=2,
            group_description="test_group",
            item_description="item",
        )

        # Check all groups processed
        assert set(results.keys()) == {"group_a", "group_b", "group_c"}

        # Check group_a results
        assert len(results["group_a"]) == 3
        for i, (item, result) in enumerate(results["group_a"]):
            assert item == f"a{i + 1}"
            assert result == f"processed_a{i + 1}"

        # Check group_b results
        assert len(results["group_b"]) == 2
        assert results["group_b"][0] == ("b1", "processed_b1")
        assert results["group_b"][1] == ("b2", "processed_b2")

        # Check group_c results
        assert len(results["group_c"]) == 1
        assert results["group_c"][0] == ("c1", "processed_c1")

    async def test_skip_groups(self):
        """Test skipping specified groups."""
        processed_items = []

        async def process_item(item: str) -> str:
            processed_items.append(item)
            return f"processed_{item}"

        items_by_group = {
            "group_a": ["a1", "a2"],
            "group_b": ["b1", "b2"],
            "group_c": ["c1", "c2"],
        }

        results = await process_grouped_items(
            items_by_group, process_item, skip_groups={"group_b", "group_c"}
        )

        # Only group_a should be processed
        assert set(results.keys()) == {"group_a"}
        assert sorted(processed_items) == ["a1", "a2"]

    async def test_empty_groups(self):
        """Test handling of empty groups."""

        async def process_item(item: str) -> str:
            return f"processed_{item}"

        items_by_group = {
            "group_a": ["a1"],
            "group_b": [],  # Empty group
            "group_c": ["c1"],
        }

        results = await process_grouped_items(items_by_group, process_item)

        # Empty group should not appear in results
        assert set(results.keys()) == {"group_a", "group_c"}

    async def test_grouped_with_errors(self):
        """Test error handling in grouped processing."""

        async def process_item(item: str) -> str:
            if "fail" in item:
                raise ValueError(f"Failed: {item}")
            return f"processed_{item}"

        items_by_group = {
            "group_a": ["a1", "a2_fail", "a3"],
            "group_b": ["b1", "b2"],
        }

        results = await process_grouped_items(items_by_group, process_item, batch_size=2)

        # Check group_a has mix of success and failure
        assert len(results["group_a"]) == 3
        assert results["group_a"][0] == ("a1", "processed_a1")
        assert isinstance(results["group_a"][1][1], ValueError)
        assert results["group_a"][2] == ("a3", "processed_a3")

        # Check group_b all successful
        assert len(results["group_b"]) == 2
        assert all(not isinstance(r[1], Exception) for r in results["group_b"])

    async def test_empty_items_dict(self):
        """Test processing empty dictionary."""

        async def process_item(item: str) -> str:
            return f"processed_{item}"

        results = await process_grouped_items({}, process_item)

        assert results == {}

    async def test_custom_context_in_grouped(self):
        """Test custom error context in grouped processing."""

        async def process_item(item: dict[str, Any]) -> str:
            if item["error"]:
                raise ValueError(f"Failed: {item['id']}")
            return f"processed_{item['id']}"

        def get_context(item: dict[str, Any]) -> dict[str, Any]:
            return {"id": item["id"], "group": item["group"]}

        items_by_group = {
            "type_a": [
                {"id": "a1", "group": "type_a", "error": False},
                {"id": "a2", "group": "type_a", "error": True},
            ],
            "type_b": [
                {"id": "b1", "group": "type_b", "error": False},
            ],
        }

        results = await process_grouped_items(
            items_by_group, process_item, error_context_func=get_context
        )

        # Verify results structure
        assert len(results["type_a"]) == 2
        assert isinstance(results["type_a"][1][1], ValueError)


class TestExtractSuccessfulResults:
    """Test extract_successful_results functionality."""

    def test_extract_all_successful(self):
        """Test extracting results when all are successful."""
        results = [
            ("item1", "result1"),
            ("item2", "result2"),
            ("item3", "result3"),
        ]

        successful = extract_successful_results(results)
        assert successful == ["result1", "result2", "result3"]

    def test_extract_with_exceptions(self):
        """Test extracting results with some exceptions."""
        results = [
            ("item1", "result1"),
            ("item2", ValueError("Failed")),
            ("item3", "result3"),
            ("item4", RuntimeError("Another failure")),
            ("item5", "result5"),
        ]

        successful = extract_successful_results(results)
        assert successful == ["result1", "result3", "result5"]

    def test_extract_all_failed(self):
        """Test extracting when all results are exceptions."""
        results = [
            ("item1", ValueError("Failed 1")),
            ("item2", RuntimeError("Failed 2")),
            ("item3", TypeError("Failed 3")),
        ]

        successful = extract_successful_results(results)
        assert successful == []

    def test_extract_empty_results(self):
        """Test extracting from empty results."""
        successful = extract_successful_results([])
        assert successful == []

    def test_extract_mixed_types(self):
        """Test extracting with various result types."""
        results = [
            ("item1", 42),
            ("item2", "string_result"),
            ("item3", ValueError("Failed")),
            ("item4", {"key": "value"}),
            ("item5", [1, 2, 3]),
            ("item6", RuntimeError("Error")),
            ("item7", None),
        ]

        successful = extract_successful_results(results)
        assert successful == [42, "string_result", {"key": "value"}, [1, 2, 3], None]
