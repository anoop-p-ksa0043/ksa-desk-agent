from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from desk_agent.domain.labeler import (
    _extract_domain,
    _label_name,
    apply_domain_label,
)
import desk_agent.domain.labeler as labeler_module


# ------------------------------------------------------------------ unit helpers

def test_extract_domain_valid():
    assert _extract_domain("john@acme.com") == "acme.com"


def test_extract_domain_no_at():
    assert _extract_domain("notanemail") is None


def test_extract_domain_normalises_case():
    assert _extract_domain("USER@ACME.COM") == "acme.com"


def test_label_name_format():
    assert _label_name("acme.com") == "domain:acme.com"


# ------------------------------------------------------------------ integration

@pytest.fixture(autouse=True)
def clear_label_cache():
    """Reset the in-process label cache between tests."""
    labeler_module._label_cache.clear()
    yield
    labeler_module._label_cache.clear()


@pytest.mark.asyncio
async def test_apply_domain_label_creates_and_assigns():
    with patch("desk_agent.domain.labeler.zoho_mcp") as mock_mcp:
        mock_mcp.call_tool = AsyncMock(side_effect=[
            {"data": []},                                           # getLabels → empty
            {"id": "lbl_001", "name": "domain:acme.com"},          # createLabel
            {},                                                     # updateTicket
        ])
        result = await apply_domain_label("ticket_1", "alice@acme.com")

    assert result == "domain:acme.com"
    calls = [c.args[0] for c in mock_mcp.call_tool.call_args_list]
    assert calls == ["ZohoDesk_getLabels", "ZohoDesk_createLabel", "ZohoDesk_updateTicket"]


@pytest.mark.asyncio
async def test_apply_domain_label_reuses_existing_label():
    with patch("desk_agent.domain.labeler.zoho_mcp") as mock_mcp:
        mock_mcp.call_tool = AsyncMock(side_effect=[
            {"data": [{"id": "lbl_002", "name": "domain:acme.com"}]},  # getLabels → found
            {},                                                         # updateTicket
        ])
        result = await apply_domain_label("ticket_2", "bob@acme.com")

    assert result == "domain:acme.com"
    calls = [c.args[0] for c in mock_mcp.call_tool.call_args_list]
    assert "ZohoDesk_createLabel" not in calls


@pytest.mark.asyncio
async def test_apply_domain_label_skips_freemail():
    with patch("desk_agent.domain.labeler.zoho_mcp") as mock_mcp:
        mock_mcp.call_tool = AsyncMock()
        result = await apply_domain_label("ticket_3", "user@gmail.com")

    assert result is None
    mock_mcp.call_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_domain_label_skips_missing_email():
    with patch("desk_agent.domain.labeler.zoho_mcp") as mock_mcp:
        mock_mcp.call_tool = AsyncMock()
        result = await apply_domain_label("ticket_4", None)

    assert result is None
    mock_mcp.call_tool.assert_not_awaited()
