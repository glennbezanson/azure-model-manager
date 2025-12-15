#!/usr/bin/env python3
"""
Azure Pricing Bridge Diagnostic

Tests the hypothesis that model.skus[].cost[].meter_id in the ARM Model Catalog API
matches the meterId field in the Retail Prices API.

Usage:
    az login
    python azure_pricing_dump.py
"""

import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import os
import requests
from typing import Dict, List, Set, Any, Optional

from azure.identity import DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient


def get_retail_prices(service_name: str = "Azure OpenAI", region: str = "eastus") -> List[Dict]:
    """Fetch retail prices from Azure public API (no auth required)."""
    print(f"\n📊 Fetching retail prices for {service_name} in {region}...")

    base_url = "https://prices.azure.com/api/retail/prices"
    filter_query = f"serviceName eq '{service_name}' and armRegionName eq '{region}'"

    all_items = []
    next_page = f"{base_url}?$filter={filter_query}"

    while next_page:
        response = requests.get(next_page)
        response.raise_for_status()
        data = response.json()
        all_items.extend(data.get("Items", []))
        next_page = data.get("NextPageLink")
        print(f"  Fetched {len(all_items)} price entries...")

    print(f"✅ Total retail prices: {len(all_items)}")
    return all_items


def get_model_catalog(subscription_id: str, location: str = "eastus") -> List[Dict]:
    """Fetch model catalog from ARM API."""
    print(f"\n📚 Fetching model catalog for subscription {subscription_id[:8]}... in {location}...")

    credential = DefaultAzureCredential()
    client = CognitiveServicesManagementClient(credential, subscription_id)

    models = []
    for model_data in client.models.list(location=location):
        # Convert to dict for easier inspection
        model_dict = {
            "kind": getattr(model_data, "kind", None),
            "sku_name": getattr(model_data, "sku_name", None),
        }

        # Extract model info
        if hasattr(model_data, "model") and model_data.model:
            model_info = model_data.model
            model_dict["model"] = {
                "name": getattr(model_info, "name", None),
                "version": getattr(model_info, "version", None),
                "format": getattr(model_info, "format", None),
                "publisher": getattr(model_info, "publisher", None),
            }

            # Extract SKUs - THIS IS THE KEY PART
            if hasattr(model_info, "skus") and model_info.skus:
                model_dict["skus"] = []
                for sku in model_info.skus:
                    sku_dict = {
                        "name": getattr(sku, "name", None),
                        "usage_name": getattr(sku, "usage_name", None),
                        "capacity": {
                            "default": getattr(sku.capacity, "default", None) if hasattr(sku, "capacity") and sku.capacity else None,
                            "maximum": getattr(sku.capacity, "maximum", None) if hasattr(sku, "capacity") and sku.capacity else None,
                        } if hasattr(sku, "capacity") else None,
                    }

                    # Look for cost/meter info
                    if hasattr(sku, "cost") and sku.cost:
                        sku_dict["cost"] = []
                        for cost in sku.cost:
                            cost_dict = {
                                "meter_id": getattr(cost, "meter_id", None),
                                "quantity": getattr(cost, "quantity", None),
                                "extended_unit": getattr(cost, "extended_unit", None),
                            }
                            # Try to get any other attributes
                            for attr in dir(cost):
                                if not attr.startswith("_"):
                                    val = getattr(cost, attr, None)
                                    if val is not None and not callable(val):
                                        cost_dict[attr] = val
                            sku_dict["cost"].append(cost_dict)

                    model_dict["skus"].append(sku_dict)

        # Extract capabilities
        if hasattr(model_data, "capabilities") and model_data.capabilities:
            caps = model_data.capabilities
            model_dict["capabilities"] = {
                "chat_completion": getattr(caps, "chat_completion", None),
                "completion": getattr(caps, "completion", None),
                "embeddings": getattr(caps, "embeddings", None),
                "vision": getattr(caps, "vision", None),
                "function_calling": getattr(caps, "function_calling", None),
            }

        models.append(model_dict)

    print(f"✅ Total models: {len(models)}")
    return models


def extract_meter_ids_from_catalog(models: List[Dict]) -> Set[str]:
    """Extract all meter IDs from model catalog."""
    meter_ids = set()
    for model in models:
        for sku in model.get("skus", []):
            for cost in sku.get("cost", []):
                meter_id = cost.get("meter_id")
                if meter_id:
                    meter_ids.add(meter_id)
    return meter_ids


def extract_meter_ids_from_retail(prices: List[Dict]) -> Set[str]:
    """Extract all meter IDs from retail prices."""
    return {p.get("meterId") for p in prices if p.get("meterId")}


def analyze_bridge(models: List[Dict], prices: List[Dict]) -> Dict:
    """Analyze if meter IDs bridge the two APIs."""
    catalog_meter_ids = extract_meter_ids_from_catalog(models)
    retail_meter_ids = extract_meter_ids_from_retail(prices)

    overlap = catalog_meter_ids & retail_meter_ids

    return {
        "catalog_meter_ids_count": len(catalog_meter_ids),
        "retail_meter_ids_count": len(retail_meter_ids),
        "overlap_count": len(overlap),
        "overlap_meter_ids": list(overlap)[:20],  # First 20 for display
        "catalog_only": list(catalog_meter_ids - retail_meter_ids)[:10],
        "retail_only": list(retail_meter_ids - catalog_meter_ids)[:10],
    }


def main():
    # Get subscription ID from environment or Azure CLI config
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID")
    if not subscription_id:
        # Try to get from az cli
        import subprocess
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True, text=True
        )
        subscription_id = result.stdout.strip()

    if not subscription_id:
        print("❌ No subscription ID found. Set AZURE_SUBSCRIPTION_ID or run 'az login'")
        return

    print("=" * 60)
    print("Azure Pricing Bridge Diagnostic")
    print("=" * 60)

    # Fetch data
    retail_prices = get_retail_prices()
    model_catalog = get_model_catalog(subscription_id)

    # Save raw data for inspection
    with open("retail_prices_dump.json", "w") as f:
        json.dump(retail_prices, f, indent=2, default=str)
    print("\n💾 Saved retail_prices_dump.json")

    with open("model_catalog_dump.json", "w") as f:
        json.dump(model_catalog, f, indent=2, default=str)
    print("💾 Saved model_catalog_dump.json")

    # Show sample entries
    print("\n" + "=" * 60)
    print("SAMPLE DATA")
    print("=" * 60)

    if retail_prices:
        print("\n📊 Sample Retail Price Entry:")
        print(json.dumps(retail_prices[0], indent=2, default=str))

    # Find a model with SKUs/cost info
    model_with_skus = None
    for m in model_catalog:
        if m.get("skus") and any(s.get("cost") for s in m.get("skus", [])):
            model_with_skus = m
            break

    if model_with_skus:
        print("\n📚 Sample Model Catalog Entry (with SKUs/cost):")
        print(json.dumps(model_with_skus, indent=2, default=str))
    else:
        print("\n⚠️  No models found with SKU/cost info")
        if model_catalog:
            print("\n📚 Sample Model Catalog Entry (no cost info):")
            print(json.dumps(model_catalog[0], indent=2, default=str))

    # Analyze bridge
    print("\n" + "=" * 60)
    print("METER ID BRIDGE ANALYSIS")
    print("=" * 60)

    analysis = analyze_bridge(model_catalog, retail_prices)

    print(f"\n  Catalog meter IDs found: {analysis['catalog_meter_ids_count']}")
    print(f"  Retail meter IDs found:  {analysis['retail_meter_ids_count']}")
    print(f"\n  *** OVERLAP: {analysis['overlap_count']} meter IDs match! ***")

    if analysis["overlap_count"] > 0:
        print("\n✅ BRIDGE FOUND! Meter IDs can join the APIs.")
        print("\nMatched Meter IDs (first 10):")
        for mid in analysis["overlap_meter_ids"][:10]:
            # Find corresponding entries
            retail_entry = next((p for p in retail_prices if p.get("meterId") == mid), None)
            if retail_entry:
                print(f"  {mid[:20]}... → {retail_entry.get('meterName')} @ ${retail_entry.get('unitPrice')}")
    else:
        print("\n⚠️  NO BRIDGE FOUND via meter IDs")
        print("Will need to fall back to name pattern matching.")

        if analysis["catalog_meter_ids_count"] == 0:
            print("\n  (Model catalog has no meter_id fields in SKU costs)")

    # Save analysis
    with open("pricing_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)
    print("\n💾 Saved pricing_analysis.json")

    # Show some retail prices for Claude/Anthropic if available
    print("\n" + "=" * 60)
    print("ANTHROPIC/CLAUDE MODELS IN RETAIL PRICES")
    print("=" * 60)

    claude_prices = [p for p in retail_prices if "claude" in p.get("meterName", "").lower()
                     or "anthropic" in p.get("meterName", "").lower()
                     or "claude" in p.get("productName", "").lower()]

    if claude_prices:
        print(f"\nFound {len(claude_prices)} Claude/Anthropic price entries:")
        for p in claude_prices[:10]:
            print(f"  {p.get('meterName')}: ${p.get('unitPrice')} per {p.get('unitOfMeasure')}")
    else:
        print("\n  No Claude/Anthropic models found in Azure OpenAI pricing.")
        print("  (They may be under a different serviceName)")

        # Try fetching AI Services pricing
        print("\n  Trying 'Azure AI services' pricing...")
        ai_prices = get_retail_prices(service_name="Azure AI services", region="eastus")
        claude_ai = [p for p in ai_prices if "claude" in p.get("meterName", "").lower()]
        if claude_ai:
            print(f"\n  Found {len(claude_ai)} Claude entries in Azure AI services:")
            for p in claude_ai[:10]:
                print(f"    {p.get('meterName')}: ${p.get('unitPrice')} per {p.get('unitOfMeasure')}")


if __name__ == "__main__":
    main()
