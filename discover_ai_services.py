#!/usr/bin/env python3
"""
Discover AI-related service names in Azure Retail Prices API.

The 'Azure OpenAI' filter returns 0 results - likely rebranded.
This script searches unfiltered results for AI-related pricing.
"""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json
from collections import defaultdict

def search_unfiltered(max_pages: int = 100):
    """Search unfiltered results for AI/OpenAI references."""

    url = "https://prices.azure.com/api/retail/prices"

    ai_keywords = ['openai', 'gpt', 'dall-e', 'whisper', 'embedding', 'o1-', 'o3-',
                   'claude', 'llama', 'mistral', 'foundry', 'cognitive']

    found_services = defaultdict(list)
    pages = 0
    total_items = 0

    print("Searching Retail Prices API (unfiltered)...")
    print("Looking for AI-related keywords in productName/meterName")
    print("-" * 60)

    while pages < max_pages:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break

        data = response.json()
        items = data.get("Items", [])
        total_items += len(items)

        for item in items:
            product = item.get('productName', '').lower()
            meter = item.get('meterName', '').lower()
            service = item.get('serviceName', '')

            # Check for AI keywords
            text = f"{product} {meter}"
            for keyword in ai_keywords:
                if keyword in text:
                    key = f"{service} | {item.get('productName')}"
                    if len(found_services[key]) < 3:  # Keep max 3 examples per product
                        found_services[key].append({
                            'serviceName': service,
                            'productName': item.get('productName'),
                            'meterName': item.get('meterName'),
                            'retailPrice': item.get('retailPrice'),
                            'unitOfMeasure': item.get('unitOfMeasure'),
                            'armRegionName': item.get('armRegionName'),
                        })
                    break

        next_page = data.get("NextPageLink")
        if not next_page:
            print(f"Reached end of results at page {pages}")
            break
        url = next_page
        pages += 1

        if pages % 20 == 0:
            print(f"  Page {pages}, scanned {total_items} items, found {len(found_services)} AI products...")

    print(f"\nScanned {total_items} total price entries across {pages} pages")
    print(f"Found {len(found_services)} AI-related products")
    print("=" * 60)

    if found_services:
        # Group by service name
        by_service = defaultdict(list)
        for key, examples in found_services.items():
            service = examples[0]['serviceName']
            by_service[service].extend(examples)

        print("\nAI SERVICES FOUND:")
        print("-" * 60)

        for service, items in sorted(by_service.items()):
            print(f"\n*** {service} ***")
            seen_products = set()
            for item in items:
                product = item['productName']
                if product not in seen_products:
                    seen_products.add(product)
                    print(f"  {product}")
                    print(f"    Meter: {item['meterName']}")
                    print(f"    Price: ${item['retailPrice']} / {item['unitOfMeasure']}")
                    print(f"    Region: {item['armRegionName']}")

        # Save full results
        with open("ai_services_found.json", "w") as f:
            json.dump(dict(found_services), f, indent=2)
        print(f"\nFull results saved to ai_services_found.json")

        # Show the filter to use
        print("\n" + "=" * 60)
        print("RECOMMENDED FILTERS:")
        print("-" * 60)
        for service in sorted(by_service.keys()):
            print(f"  serviceName eq '{service}'")
    else:
        print("\nNo AI-related pricing found in scanned pages.")
        print("Try increasing max_pages or the API may have changed structure.")

    return found_services


def test_service_families():
    """Check what service families exist."""
    print("\n" + "=" * 60)
    print("CHECKING SERVICE FAMILIES")
    print("=" * 60)

    url = "https://prices.azure.com/api/retail/prices"

    families = set()
    response = requests.get(url)
    data = response.json()

    for item in data.get("Items", []):
        families.add(item.get('serviceFamily', 'Unknown'))

    print("\nService Families in first page:")
    for f in sorted(families):
        print(f"  {f}")

    # Try AI + Machine Learning family
    print("\n--- Testing 'AI + Machine Learning' family ---")
    params = {"$filter": "serviceFamily eq 'AI + Machine Learning'"}
    response = requests.get("https://prices.azure.com/api/retail/prices", params=params)

    if response.status_code == 200:
        data = response.json()
        items = data.get("Items", [])
        print(f"Found {len(items)} items in AI + ML family")

        if items:
            services = set(i.get('serviceName') for i in items)
            print("Services in this family:")
            for s in sorted(services):
                print(f"  {s}")


if __name__ == "__main__":
    test_service_families()
    search_unfiltered(max_pages=50)  # Limit pages for speed
