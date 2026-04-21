"""Tests for lookup_fedramp_marketplace_products."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent.tools.lookup_fedramp_marketplace_products import (
    LookupFedrampMarketplaceProducts,
    LookupFedrampMarketplaceProductsInput,
)


@pytest.mark.asyncio
async def test_fedramp_tool_finds_match() -> None:
    payload = {
        "data": {
            "Products": [
                {
                    "fedramp_id": "F000TEST01",
                    "name": "Acme Federal Platform",
                    "cloud_service_provider": "Acme Inc",
                    "cloud_service_offering": "GovCloud",
                    "status": "FedRAMP Authorized",
                    "service_description": "Federal workloads.",
                }
            ]
        }
    }
    body = json.dumps(payload)
    final = "https://www.fedramp.gov/marketplace/products.json"
    with (
        patch(
            "agent.tools.lookup_fedramp_marketplace_products._robots_allows",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.tools.lookup_fedramp_marketplace_products._fetch_catalog_text",
            new_callable=AsyncMock,
            return_value=(body, final),
        ),
    ):
        tool = LookupFedrampMarketplaceProducts()
        out = await tool.run(LookupFedrampMarketplaceProductsInput(search_phrase="Acme"))
    assert out.error is None
    assert out.marketplace_resolution == "matches_found"
    assert len(out.matches) == 1
    m0 = out.matches[0]
    assert m0.fedramp_id == "F000TEST01"
    assert m0.marketplace_status == "FedRAMP Authorized"
    assert str(m0.detail_url).startswith("https://www.fedramp.gov/marketplace/products/F000TEST01")


@pytest.mark.asyncio
async def test_fedramp_tool_empty_matches_is_success() -> None:
    payload = {
        "data": {
            "Products": [
                {
                    "fedramp_id": "FZZZOTHER",
                    "name": "Totally Unrelated Vendor",
                    "cloud_service_provider": "Other LLC",
                    "cloud_service_offering": "Thing",
                    "status": "FedRAMP Ready",
                    "service_description": "Nothing about the query phrase.",
                }
            ]
        }
    }
    body = json.dumps(payload)
    with (
        patch(
            "agent.tools.lookup_fedramp_marketplace_products._robots_allows",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch(
            "agent.tools.lookup_fedramp_marketplace_products._fetch_catalog_text",
            new_callable=AsyncMock,
            return_value=(
                body,
                "https://www.fedramp.gov/marketplace/products.json",
            ),
        ),
    ):
        tool = LookupFedrampMarketplaceProducts()
        out = await tool.run(
            LookupFedrampMarketplaceProductsInput(search_phrase="ZyzzyvaNonexistentCorp")
        )
    assert out.error is None
    assert out.marketplace_resolution == "no_marketplace_listing"
    assert out.matches == []
