#!/usr/bin/env python3
"""
Azure Marketplace Offer ID Discovery - API Testing Method

Discovers valid offer IDs by testing various naming patterns against
the Marketplace pricing API. No browser required.

Usage:
    python discover_offers_api.py                    # Test all patterns
    python discover_offers_api.py --publisher meta   # Only Meta models
    python discover_offers_api.py --output offers.json

Output:
    discovered_offers.json - Valid offer IDs and pricing data
"""

import requests
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed


# =============================================================================
# OFFER ID PATTERNS TO TEST
# =============================================================================

# Different publishers use different naming conventions
# We'll try multiple patterns for each model

PUBLISHER_PATTERNS = {
    # Pattern: (prefix, separator, suffix)
    "anthropic": [
        ("{pub}.{pub}-{model}-offer", True),      # anthropic.anthropic-claude-opus-4-5-offer (KNOWN WORKING)
    ],
    "meta": [
        ("{pub}.{pub}-{model}-offer", True),       # meta.meta-llama-3-1-70b-instruct-offer
        ("{pub}.{model}-offer", True),             # meta.llama-3-1-70b-instruct-offer
        ("{pub}.llama-{ver}-offer", False),        # meta.llama-3-1-offer (generic)
        ("meta-llama.{model}-offer", True),        # meta-llama.llama-3-1-70b-instruct-offer
        ("facebook.{model}-offer", True),          # facebook.llama-3-1-70b-instruct-offer
    ],
    "mistralai": [
        ("{pub}.{pub}-{model}-offer", True),       # mistralai.mistralai-mistral-large-offer
        ("{pub}.{model}-offer", True),             # mistralai.mistral-large-offer
        ("mistral.{model}-offer", True),           # mistral.mistral-large-offer
        ("{pub}.mistral-{model}-offer", True),     # mistralai.mistral-large-offer
    ],
    "cohere": [
        ("{pub}.{pub}-{model}-offer", True),       # cohere.cohere-command-r-plus-offer
        ("{pub}.{model}-offer", True),             # cohere.command-r-plus-offer
    ],
    "ai21labs": [
        ("{pub}.{pub}-{model}-offer", True),       # ai21labs.ai21labs-jamba-1-5-large-offer
        ("{pub}.ai21-{model}-offer", True),        # ai21labs.ai21-jamba-1-5-large-offer
        ("{pub}.{model}-offer", True),             # ai21labs.jamba-1-5-large-offer
        ("ai21.{model}-offer", True),              # ai21.jamba-1-5-large-offer
    ],
    "nvidia": [
        ("{pub}.{pub}-{model}-offer", True),
        ("{pub}.{model}-offer", True),
    ],
    "databricks": [
        ("{pub}.{pub}-{model}-offer", True),
        ("{pub}.{model}-offer", True),
    ],
}


# Models to test by publisher
MODELS_BY_PUBLISHER = {
    "anthropic": [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-1",
        "claude-sonnet-4",
        "claude-3-7-sonnet",
        "claude-3-5-sonnet",
        "claude-3-5-sonnet-v2",
        "claude-3-5-haiku",
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
    ],
    "meta": [
        "llama-3-3-70b-instruct",
        "llama-3-2-90b-vision-instruct",
        "llama-3-2-11b-vision-instruct",
        "llama-3-2-3b-instruct",
        "llama-3-2-1b-instruct",
        "llama-3-1-405b-instruct",
        "llama-3-1-70b-instruct",
        "llama-3-1-8b-instruct",
        "llama-3-70b-instruct",
        "llama-3-8b-instruct",
        "meta-llama-3-3-70b-instruct",
        "meta-llama-3-1-405b-instruct",
        "meta-llama-3-1-70b-instruct",
        "meta-llama-3-1-8b-instruct",
    ],
    "mistralai": [
        "mistral-large-2411",
        "mistral-large-2407",
        "mistral-large",
        "mistral-small-2409",
        "mistral-small",
        "mistral-nemo-2407",
        "mistral-nemo",
        "codestral-2405",
        "codestral",
        "ministral-3b-2410",
        "ministral-3b",
        "ministral-8b-2410",
        "ministral-8b",
        "pixtral-12b-2409",
        "pixtral-12b",
        "pixtral-large-2411",
        "pixtral-large",
    ],
    "cohere": [
        "command-r-plus-08-2024",
        "command-r-plus",
        "command-r-08-2024",
        "command-r",
        "command",
        "command-light",
        "embed-v3-english",
        "embed-v3-multilingual",
        "embed-english-v3",
        "embed-multilingual-v3",
        "rerank-v3-english",
        "rerank-v3-multilingual",
        "cohere-command-r-plus",
        "cohere-command-r",
        "cohere-embed-v3-english",
    ],
    "ai21labs": [
        "jamba-1-5-large",
        "jamba-1-5-mini",
        "jamba-instruct",
        "j2-ultra",
        "j2-mid",
        "ai21-jamba-1-5-large",
        "ai21-jamba-1-5-mini",
    ],
    "nvidia": [
        "nemotron-4-340b-instruct",
        "llama-3-1-nemotron-70b-instruct",
        "nvidia-nemotron-4-340b-instruct",
    ],
}


# =============================================================================
# API FUNCTIONS
# =============================================================================

def test_offer_id(offer_id: str, market: str = "us", timeout: int = 10) -> Tuple[bool, Optional[dict]]:
    """
    Test if an offer ID returns valid pricing data.

    Returns:
        (success, pricing_data) tuple
    """
    url = f"https://marketplace.microsoft.com/view/appPricing/{offer_id}/{market}"

    try:
        response = requests.get(url, timeout=timeout)

        if response.status_code == 200:
            data = response.json()

            # Check if we got actual pricing data (not empty or error)
            if data and isinstance(data, (list, dict)):
                # Check for meters/pricing info
                if isinstance(data, list) and len(data) > 0:
                    return True, data
                elif isinstance(data, dict):
                    if data.get('meters') or data.get('pricingData') or data.get('plans') or data.get('skus'):
                        return True, data
                    # Sometimes just having the response is enough
                    if len(data) > 0:
                        return True, data

        return False, None

    except requests.exceptions.Timeout:
        return False, None
    except requests.exceptions.RequestException:
        return False, None
    except json.JSONDecodeError:
        return False, None


def generate_offer_ids(publisher: str, model: str) -> List[str]:
    """Generate possible offer ID variations for a model."""
    offer_ids = []

    patterns = PUBLISHER_PATTERNS.get(publisher, [
        ("{pub}.{pub}-{model}-offer", True),
        ("{pub}.{model}-offer", True),
    ])

    for pattern, use_model in patterns:
        if use_model:
            offer_id = pattern.format(pub=publisher, model=model)
            offer_ids.append(offer_id)

            # Also try with 'azure-' prefix
            offer_ids.append(f"azure-{offer_id}")

            # Try lowercase variations
            offer_ids.append(offer_id.lower())

    # Add some generic variations
    offer_ids.extend([
        f"{publisher}.{model}",
        f"{publisher}-{model}",
        f"{model}",
    ])

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for oid in offer_ids:
        if oid not in seen:
            seen.add(oid)
            unique.append(oid)

    return unique


def discover_offer_id(publisher: str, model: str, verbose: bool = True) -> Optional[Tuple[str, dict]]:
    """
    Discover the correct offer ID for a model by testing patterns.

    Returns:
        (offer_id, pricing_data) if found, None otherwise
    """
    offer_ids = generate_offer_ids(publisher, model)

    if verbose:
        print(f"\nTesting {publisher}/{model}...")

    for offer_id in offer_ids:
        success, data = test_offer_id(offer_id)

        if success:
            if verbose:
                print(f"  + FOUND: {offer_id}")
            return offer_id, data
        else:
            if verbose:
                print(f"  - {offer_id}")

        # Small delay to avoid rate limiting
        time.sleep(0.2)

    return None


def discover_all(publishers: List[str] = None, verbose: bool = True) -> Dict[str, dict]:
    """
    Discover offer IDs for all configured models.

    Returns:
        Dict mapping model names to {offer_id, publisher, pricing} objects
    """
    discovered = {}
    not_found = []

    for publisher, models in MODELS_BY_PUBLISHER.items():
        if publishers and publisher not in publishers:
            continue

        print(f"\n{'='*60}")
        print(f"Publisher: {publisher.upper()}")
        print(f"{'='*60}")

        for model in models:
            result = discover_offer_id(publisher, model, verbose=verbose)

            if result:
                offer_id, pricing = result
                discovered[model] = {
                    "offer_id": offer_id,
                    "publisher": publisher,
                    "has_pricing": bool(pricing),
                    "meter_count": len(pricing) if isinstance(pricing, list) else None,
                }
            else:
                not_found.append(f"{publisher}/{model}")

    return discovered, not_found


def extract_pricing_summary(pricing_data: dict) -> dict:
    """Extract pricing summary from API response."""
    summary = {
        "input_per_1k": None,
        "output_per_1k": None,
        "meters": [],
    }

    meters = []
    if isinstance(pricing_data, list):
        meters = pricing_data
    elif isinstance(pricing_data, dict):
        meters = pricing_data.get('meters', pricing_data.get('pricingData', []))
        # Handle nested structure
        if not meters and 'skus' in pricing_data:
            for sku in pricing_data.get('skus', []):
                for term in sku.get('termPrices', []):
                    meters.extend(term.get('customMeter', []))

    for meter in meters:
        name = meter.get('meterName', meter.get('name', meter.get('title', ''))).lower()
        price = meter.get('price', meter.get('unitPrice', meter.get('rate', 0)))

        summary["meters"].append({
            "name": name,
            "price": price,
        })

        if 'input' in name and summary["input_per_1k"] is None:
            summary["input_per_1k"] = price
        elif 'output' in name and summary["output_per_1k"] is None:
            summary["output_per_1k"] = price

    return summary


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Discover Azure Marketplace offer IDs via API")
    parser.add_argument("--publisher", type=str, help="Filter by publisher")
    parser.add_argument("--model", type=str, help="Test specific model")
    parser.add_argument("--output", type=str, default="discovered_offers.json", help="Output file")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--with-pricing", action="store_true", help="Also fetch and store pricing data")

    args = parser.parse_args()

    print("Azure Marketplace Offer ID Discovery")
    print("=" * 60)
    print("Testing offer ID patterns against pricing API...")

    # Filter publishers if specified
    publishers = [args.publisher] if args.publisher else None

    # Run discovery
    discovered, not_found = discover_all(publishers=publishers, verbose=not args.quiet)

    # Optionally fetch full pricing data
    if args.with_pricing:
        print("\n\nFetching full pricing data...")
        for model, data in discovered.items():
            success, pricing = test_offer_id(data["offer_id"])
            if success and pricing:
                data["pricing"] = extract_pricing_summary(pricing)
                data["raw_pricing"] = pricing

    # Build output
    output = {
        "generated_at": datetime.now().isoformat(),
        "method": "api_pattern_testing",
        "total_discovered": len(discovered),
        "total_not_found": len(not_found),
        "discovered": discovered,
        "not_found": not_found,
    }

    # Generate Python code snippet
    python_code = ["", "# Copy this to MARKETPLACE_OFFERS in unified_pricing.py:", ""]
    python_code.append("DISCOVERED_OFFERS = {")

    by_pub = {}
    for model, data in discovered.items():
        pub = data["publisher"]
        if pub not in by_pub:
            by_pub[pub] = []
        by_pub[pub].append((model, data["offer_id"]))

    for pub in sorted(by_pub.keys()):
        python_code.append(f"    # {pub.upper()}")
        for model, offer_id in sorted(by_pub[pub]):
            python_code.append(f'    "{model}": "{offer_id}",')
        python_code.append("")

    python_code.append("}")
    output["python_code"] = "\n".join(python_code)

    # Save results
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("DISCOVERY SUMMARY")
    print("=" * 60)
    print(f"Total discovered: {len(discovered)}")
    print(f"Total not found:  {len(not_found)}")
    print(f"Output saved to:  {args.output}")

    if discovered:
        print("\nDiscovered offer IDs:")
        for model, data in sorted(discovered.items()):
            print(f"  {model}: {data['offer_id']}")

    if not_found:
        print(f"\nNot found ({len(not_found)}):")
        for item in not_found[:10]:
            print(f"  {item}")
        if len(not_found) > 10:
            print(f"  ... and {len(not_found) - 10} more")

    print("\n" + output["python_code"])


if __name__ == "__main__":
    main()
