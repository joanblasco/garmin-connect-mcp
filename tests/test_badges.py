"""Tests for query_badges (paginated achievement badges, distinct from badge challenges)."""

import json

from garmin_connect_mcp.tools.challenges import query_badges

BADGES = [{"badgeId": i} for i in range(12)]


def _data(response_json: str):
    return json.loads(response_json)["data"]


def _pagination(response_json: str):
    return json.loads(response_json)["pagination"]


def _error(response_json: str):
    return json.loads(response_json)["error"]


class TestStatusSelection:
    async def test_in_progress_calls_get_in_progress_badges(self, client_stub, ctx):
        client_stub._method_results["get_in_progress_badges"] = BADGES

        result = await query_badges(status="in_progress", ctx=ctx)

        assert _data(result)["total_count"] == 12
        assert any(name == "get_in_progress_badges" for name, _, _ in client_stub.calls)
        assert all(name != "get_available_badges" for name, _, _ in client_stub.calls)

    async def test_available_calls_get_available_badges(self, client_stub, ctx):
        client_stub._method_results["get_available_badges"] = BADGES

        result = await query_badges(status="available", ctx=ctx)

        assert _data(result)["total_count"] == 12
        assert any(name == "get_available_badges" for name, _, _ in client_stub.calls)

    async def test_invalid_status_is_rejected(self, ctx):
        result = await query_badges(status="bogus", ctx=ctx)

        assert _error(result)["type"] == "invalid_parameters"


class TestPagination:
    async def test_first_page_respects_limit_and_flags_has_more(self, client_stub, ctx):
        client_stub._method_results["get_in_progress_badges"] = BADGES

        result = await query_badges(status="in_progress", limit=5, ctx=ctx)

        assert len(_data(result)["badges"]) == 5
        assert _pagination(result)["has_more"] is True
        assert _pagination(result)["cursor"] is not None

    async def test_cursor_advances_to_the_next_page_without_overlap(self, client_stub, ctx):
        client_stub._method_results["get_in_progress_badges"] = BADGES

        page1 = json.loads(await query_badges(status="in_progress", limit=5, ctx=ctx))
        page2 = json.loads(
            await query_badges(
                status="in_progress", limit=5, cursor=page1["pagination"]["cursor"], ctx=ctx
            )
        )

        ids1 = {b["badgeId"] for b in page1["data"]["badges"]}
        ids2 = {b["badgeId"] for b in page2["data"]["badges"]}
        assert ids1.isdisjoint(ids2)

    async def test_last_page_has_no_more_and_no_next_cursor(self, client_stub, ctx):
        client_stub._method_results["get_in_progress_badges"] = BADGES

        # 12 badges, limit 5 -> pages of 5, 5, 2
        result = await query_badges(status="in_progress", limit=5, cursor=None, ctx=ctx)
        page2 = json.loads(
            await query_badges(
                status="in_progress",
                limit=5,
                cursor=json.loads(result)["pagination"]["cursor"],
                ctx=ctx,
            )
        )
        page3 = json.loads(
            await query_badges(
                status="in_progress",
                limit=5,
                cursor=page2["pagination"]["cursor"],
                ctx=ctx,
            )
        )

        assert len(page3["data"]["badges"]) == 2
        assert page3["pagination"]["has_more"] is False
        assert page3["pagination"]["cursor"] is None

    async def test_invalid_limit_is_rejected(self, ctx):
        result = await query_badges(status="in_progress", limit=999, ctx=ctx)

        assert _error(result)["type"] == "validation_error"

    async def test_invalid_cursor_is_rejected(self, ctx):
        result = await query_badges(status="in_progress", cursor="not-a-real-cursor", ctx=ctx)

        assert _error(result)["type"] == "validation_error"
