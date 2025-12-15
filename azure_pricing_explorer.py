#!/usr/bin/env python3
"""
Azure AI Foundry Pricing Explorer

Explores the gap between:
1. ARM Model Catalog API (what models are available)
2. Azure Retail Prices API (what they cost)

Goal: Find a reliable join key to bridge model metadata with pricing.

Requirements:
    pip install azure-identity azure-mgmt-cognitiveservices requests pandas tabulate
"""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import requests
from typing import Optional
from dataclasses import dataclass, field
from azure.identity import DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient


@dataclass
class PricingExplorer:
    """Explores Azure OpenAI pricing APIs to find join keys."""

    subscription_id: str
    location: str = "eastus"

    # Cached data
    _catalog_models: list = field(default_factory=list)
    _retail_prices: list = field(default_factory=list)
    _credential: Optional[DefaultAzureCredential] = None

    def __post_init__(self):
        self._credential = DefaultAzureCredential()

    # =========================================================================
    # API 1: ARM Model Catalog
    # =========================================================================

    def fetch_model_catalog(self) -> list:
        """
        Fetch models from ARM Model Catalog API.

        Endpoint: GET https://management.azure.com/subscriptions/{sub}/providers/
                      Microsoft.CognitiveServices/locations/{loc}/models

        Returns model metadata including SKUs with potential meter IDs.
        """
        print(f"\n{'='*60}")
        print("FETCHING MODEL CATALOG")
        print(f"Location: {self.location}")
        print(f"{'='*60}")

        client = CognitiveServicesManagementClient(
            credential=self._credential,
            subscription_id=self.subscription_id
        )

        models = []
        for model in client.models.list(location=self.location):
            model_dict = {
                'kind': model.kind,
                'sku_name': model.sku_name,
                'model_name': model.model.name if model.model else None,
                'model_format': model.model.format if model.model else None,
                'model_version': model.model.version if model.model else None,
                'publisher': getattr(model.model, 'publisher', None) if model.model else None,
                'lifecycle_status': model.model.lifecycle_status if model.model else None,
                'capabilities': dict(model.model.capabilities) if model.model and model.model.capabilities else {},
                'skus': [],
                'raw_model': model.model,
            }

            # Extract SKU details - this is where meter IDs might be
            if model.model and hasattr(model.model, 'skus') and model.model.skus:
                for sku in model.model.skus:
                    sku_info = {
                        'name': sku.name,
                        'usage_name': getattr(sku, 'usage_name', None),
                        'capacity': {
                            'min': sku.capacity.minimum if sku.capacity else None,
                            'max': sku.capacity.maximum if sku.capacity else None,
                            'step': sku.capacity.step if sku.capacity else None,
                        } if hasattr(sku, 'capacity') and sku.capacity else None,
                        'cost': [],
                    }

                    # THE KEY: Extract cost/meter info
                    if hasattr(sku, 'cost') and sku.cost:
                        for cost_item in sku.cost:
                            sku_info['cost'].append({
                                'meter_id': getattr(cost_item, 'meter_id', None),
                                'name': getattr(cost_item, 'name', None),
                                'unit': getattr(cost_item, 'unit', None),
                            })

                    model_dict['skus'].append(sku_info)

            models.append(model_dict)

        self._catalog_models = models
        print(f"Found {len(models)} models in catalog")
        return models

    # =========================================================================
    # API 2: Retail Prices
    # =========================================================================

    def fetch_retail_prices(self, service_name: str = "Azure OpenAI") -> list:
        """
        Fetch pricing from Azure Retail Prices API.

        Endpoint: GET https://prices.azure.com/api/retail/prices

        No auth required - public API.
        """
        print(f"\n{'='*60}")
        print("FETCHING RETAIL PRICES")
        print(f"Service: {service_name}")
        print(f"{'='*60}")

        base_url = "https://prices.azure.com/api/retail/prices"
        all_prices = []

        # Filter for Azure OpenAI in our region
        filter_query = f"serviceName eq '{service_name}'"
        if self.location:
            filter_query += f" and armRegionName eq '{self.location}'"

        params = {"$filter": filter_query}

        while True:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()

            items = data.get("Items", [])
            all_prices.extend(items)
            print(f"  Fetched {len(all_prices)} prices so far...")

            # Handle pagination
            next_page = data.get("NextPageLink")
            if next_page:
                base_url = next_page
                params = {}  # Next page link includes params
            else:
                break

        self._retail_prices = all_prices
        print(f"Found {len(all_prices)} price entries")
        return all_prices

    # =========================================================================
    # Analysis: Find the Join
    # =========================================================================

    def analyze_meter_ids(self):
        """
        Compare meter IDs between Model Catalog and Retail Prices.

        This is the key hypothesis: if meterId matches, we have our bridge.
        """
        print(f"\n{'='*60}")
        print("ANALYZING METER ID OVERLAP")
        print(f"{'='*60}")

        # Extract meter IDs from catalog
        catalog_meter_ids = set()
        catalog_meter_details = {}

        for model in self._catalog_models:
            for sku in model.get('skus', []):
                for cost in sku.get('cost', []):
                    meter_id = cost.get('meter_id')
                    if meter_id:
                        catalog_meter_ids.add(meter_id)
                        catalog_meter_details[meter_id] = {
                            'model': model['model_name'],
                            'sku': sku['name'],
                            'cost_name': cost.get('name'),
                            'unit': cost.get('unit'),
                        }

        # Extract meter IDs from retail prices
        retail_meter_ids = set()
        retail_meter_details = {}

        for price in self._retail_prices:
            meter_id = price.get('meterId')
            if meter_id:
                retail_meter_ids.add(meter_id)
                retail_meter_details[meter_id] = {
                    'meter_name': price.get('meterName'),
                    'product_name': price.get('productName'),
                    'sku_name': price.get('skuName'),
                    'retail_price': price.get('retailPrice'),
                    'unit': price.get('unitOfMeasure'),
                }

        # Find overlap
        overlap = catalog_meter_ids & retail_meter_ids
        catalog_only = catalog_meter_ids - retail_meter_ids
        retail_only = retail_meter_ids - catalog_meter_ids

        print(f"\nMeter IDs in Model Catalog: {len(catalog_meter_ids)}")
        print(f"Meter IDs in Retail Prices: {len(retail_meter_ids)}")
        print(f"OVERLAP (the bridge!): {len(overlap)}")
        print(f"Catalog only: {len(catalog_only)}")
        print(f"Retail only: {len(retail_only)}")

        if overlap:
            print(f"\n{'='*60}")
            print("SUCCESS! Found matching meter IDs:")
            print(f"{'='*60}")
            for meter_id in list(overlap)[:10]:  # First 10
                cat = catalog_meter_details.get(meter_id, {})
                ret = retail_meter_details.get(meter_id, {})
                print(f"\nMeter ID: {meter_id}")
                print(f"  Catalog: {cat.get('model')} / {cat.get('sku')}")
                print(f"  Retail:  {ret.get('product_name')} - {ret.get('meter_name')}")
                print(f"  Price:   ${ret.get('retail_price')} per {ret.get('unit')}")

        return {
            'overlap': overlap,
            'catalog_only': catalog_only,
            'retail_only': retail_only,
            'catalog_details': catalog_meter_details,
            'retail_details': retail_meter_details,
        }

    def analyze_name_patterns(self):
        """
        Analyze naming patterns to build fuzzy matching rules.
        """
        print(f"\n{'='*60}")
        print("ANALYZING NAME PATTERNS")
        print(f"{'='*60}")

        # Catalog model names
        catalog_names = set()
        for model in self._catalog_models:
            if model['model_name']:
                catalog_names.add(model['model_name'].lower())

        # Retail product/meter names
        retail_patterns = {}
        for price in self._retail_prices:
            product = price.get('productName', '')
            meter = price.get('meterName', '')

            # Extract model identifier from meter name
            # e.g., "GPT-4 Input Tokens" -> "gpt-4"
            parts = meter.lower().split()
            if parts:
                # Try to find model name in first 1-3 words
                for i in range(1, min(4, len(parts) + 1)):
                    candidate = '-'.join(parts[:i])
                    normalized = candidate.replace(' ', '-')
                    if normalized not in retail_patterns:
                        retail_patterns[normalized] = []
                    retail_patterns[normalized].append({
                        'product': product,
                        'meter': meter,
                        'price': price.get('retailPrice'),
                    })

        print(f"\nCatalog model names ({len(catalog_names)}):")
        for name in sorted(catalog_names)[:20]:
            print(f"  {name}")

        print(f"\nRetail patterns extracted:")
        for pattern, items in sorted(retail_patterns.items())[:20]:
            print(f"  {pattern}: {len(items)} price entries")

        # Try to match
        print(f"\n{'='*60}")
        print("ATTEMPTING NAME MATCHING")
        print(f"{'='*60}")

        matches = []
        for catalog_name in catalog_names:
            normalized_catalog = catalog_name.replace('_', '-').replace('.', '-')

            for retail_pattern in retail_patterns:
                # Various matching strategies
                if (normalized_catalog in retail_pattern or
                    retail_pattern in normalized_catalog or
                    normalized_catalog.replace('-', '') == retail_pattern.replace('-', '')):

                    matches.append({
                        'catalog': catalog_name,
                        'retail_pattern': retail_pattern,
                        'prices': retail_patterns[retail_pattern],
                    })

        print(f"Found {len(matches)} potential name matches")
        for match in matches[:10]:
            print(f"\n  Catalog: {match['catalog']}")
            print(f"  Retail:  {match['retail_pattern']}")
            if match['prices']:
                p = match['prices'][0]
                print(f"  Example: {p['meter']} @ ${p['price']}")

        return matches

    def build_unified_mapping(self) -> dict:
        """
        Build a unified mapping of models to prices using best available method.

        Priority:
        1. Meter ID match (most reliable)
        2. Name pattern match (fallback)
        """
        print(f"\n{'='*60}")
        print("BUILDING UNIFIED MODEL -> PRICE MAPPING")
        print(f"{'='*60}")

        meter_analysis = self.analyze_meter_ids()

        unified = {}

        # Method 1: Use meter ID matches
        for meter_id in meter_analysis['overlap']:
            cat = meter_analysis['catalog_details'].get(meter_id, {})
            ret = meter_analysis['retail_details'].get(meter_id, {})

            model_name = cat.get('model')
            if model_name:
                if model_name not in unified:
                    unified[model_name] = {
                        'match_method': 'meter_id',
                        'prices': {},
                    }

                meter_name = ret.get('meter_name', '')
                price_type = 'input' if 'input' in meter_name.lower() else 'output' if 'output' in meter_name.lower() else 'other'

                unified[model_name]['prices'][price_type] = {
                    'price': ret.get('retail_price'),
                    'unit': ret.get('unit'),
                    'meter_id': meter_id,
                    'sku': ret.get('sku_name'),
                }

        # Method 2: Fill gaps with name matching
        name_matches = self.analyze_name_patterns()

        for match in name_matches:
            model_name = match['catalog']
            if model_name not in unified:
                unified[model_name] = {
                    'match_method': 'name_pattern',
                    'prices': {},
                }

                for price_item in match['prices']:
                    meter = price_item['meter'].lower()
                    price_type = 'input' if 'input' in meter else 'output' if 'output' in meter else 'other'

                    if price_type not in unified[model_name]['prices']:
                        unified[model_name]['prices'][price_type] = {
                            'price': price_item['price'],
                            'meter_name': price_item['meter'],
                        }

        print(f"\nUnified mapping covers {len(unified)} models")
        return unified

    def export_findings(self, filename: str = "pricing_analysis.json"):
        """Export all findings to JSON for further analysis."""

        findings = {
            'location': self.location,
            'catalog_models': self._catalog_models,
            'retail_prices': self._retail_prices,
            'unified_mapping': self.build_unified_mapping(),
        }

        # Clean up non-serializable items
        for model in findings['catalog_models']:
            model.pop('raw_model', None)

        with open(filename, 'w') as f:
            json.dump(findings, f, indent=2, default=str)

        print(f"\nExported findings to {filename}")
        return filename


def main():
    """
    Run the exploration.

    Set your subscription ID before running:
        export AZURE_SUBSCRIPTION_ID="your-sub-id"

    Or modify directly below.
    """
    import os

    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "YOUR_SUBSCRIPTION_ID")

    # Initialize explorer
    explorer = PricingExplorer(
        subscription_id=subscription_id,
        location="eastus"  # Change as needed
    )

    # Fetch data from both APIs
    explorer.fetch_model_catalog()
    explorer.fetch_retail_prices()

    # Also try "Cognitive Services" and "Azure AI services"
    if len(explorer._retail_prices) == 0:
        print("\nNo Azure OpenAI prices found, trying 'Cognitive Services'...")
        explorer.fetch_retail_prices(service_name="Cognitive Services")

    if len(explorer._retail_prices) == 0:
        print("\nNo Cognitive Services prices found, trying 'Azure AI services'...")
        explorer.fetch_retail_prices(service_name="Azure AI services")

    # Analyze the gap
    meter_analysis = explorer.analyze_meter_ids()

    # Build unified mapping
    unified = explorer.build_unified_mapping()

    # Export for review
    explorer.export_findings()

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Models in catalog: {len(explorer._catalog_models)}")
    print(f"Price entries: {len(explorer._retail_prices)}")
    print(f"Meter ID matches: {len(meter_analysis['overlap'])}")
    print(f"Models with pricing: {len(unified)}")

    if meter_analysis['overlap']:
        print("\n[OK] METER ID BRIDGE EXISTS!")
        print("   The Model Catalog API SKU cost data contains meter IDs")
        print("   that match the Retail Prices API meterId field.")
    else:
        print("\n[!] NO METER ID OVERLAP")
        print("   Must rely on name pattern matching.")


if __name__ == "__main__":
    main()
