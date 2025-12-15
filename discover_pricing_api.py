#!/usr/bin/env python3
"""
Azure AI Foundry API Discovery

Instead of scraping page content, this captures ALL network requests
while navigating the portal, looking for the API that serves pricing data.

This is the "find the API" approach rather than "scrape the page" approach.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python discover_pricing_api.py --headed

    # Then manually navigate to model pricing in the browser
    # The script captures all API calls and saves them for analysis
"""

import asyncio
import json
import re
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
import argparse

try:
    from playwright.async_api import async_playwright, Request, Response
except ImportError:
    print("Install: pip install playwright && playwright install chromium")
    exit(1)


@dataclass
class CapturedRequest:
    """A captured API request."""
    timestamp: str
    url: str
    method: str
    resource_type: str
    request_headers: dict
    request_body: Optional[str]
    status_code: Optional[int]
    response_headers: Optional[dict]
    response_body: Optional[str]
    pricing_keywords_found: list


class APIDiscovery:
    """Captures and analyzes API traffic from Azure portal."""

    PRICING_KEYWORDS = [
        'price', 'pricing', 'cost', 'billing', 'meter',
        'rate', 'charge', 'token', 'usage', 'sku',
        'offer', 'plan', 'subscription', 'marketplace'
    ]

    MODEL_KEYWORDS = [
        'claude', 'anthropic', 'llama', 'meta', 'mistral',
        'gpt', 'openai', 'cohere', 'model', 'deployment'
    ]

    def __init__(self):
        self.captured_requests: list[CapturedRequest] = []
        self.interesting_requests: list[CapturedRequest] = []

    def find_keywords(self, text: str) -> list[str]:
        """Find pricing-related keywords in text."""
        if not text:
            return []
        text_lower = text.lower()
        found = []
        for kw in self.PRICING_KEYWORDS + self.MODEL_KEYWORDS:
            if kw in text_lower:
                found.append(kw)
        return found

    async def on_request(self, request: Request):
        """Capture outgoing request."""
        # Skip non-API requests
        if request.resource_type in ['image', 'stylesheet', 'font', 'media']:
            return

        url = request.url

        # Focus on API-like calls
        if not any(pattern in url for pattern in ['/api/', 'management.azure.com', 'ai.azure.com', 'ml.azure.com', '.azure.com/v']):
            return

        body = None
        try:
            body = request.post_data
        except:
            pass

        keywords = self.find_keywords(url) + self.find_keywords(body or '')

        captured = CapturedRequest(
            timestamp=datetime.now().isoformat(),
            url=url,
            method=request.method,
            resource_type=request.resource_type,
            request_headers=dict(request.headers),
            request_body=body,
            status_code=None,
            response_headers=None,
            response_body=None,
            pricing_keywords_found=keywords,
        )

        self.captured_requests.append(captured)

        if keywords:
            self.interesting_requests.append(captured)
            print(f"[API] {request.method} {url[:80]}...")
            print(f"   Keywords: {', '.join(keywords)}")

    async def on_response(self, response: Response):
        """Capture response and attach to request."""
        url = response.url

        # Find matching request
        for captured in reversed(self.captured_requests):
            if captured.url == url and captured.status_code is None:
                captured.status_code = response.status
                captured.response_headers = dict(response.headers)

                # Try to get response body
                try:
                    content_type = response.headers.get('content-type', '')
                    if 'json' in content_type or 'text' in content_type:
                        body = await response.text()
                        captured.response_body = body[:10000]  # Limit size

                        # Check response for pricing keywords
                        new_keywords = self.find_keywords(body)
                        if new_keywords:
                            for kw in new_keywords:
                                if kw not in captured.pricing_keywords_found:
                                    captured.pricing_keywords_found.append(kw)

                            # Print if we found pricing in response
                            if any(kw in ['price', 'pricing', 'cost', 'rate'] for kw in new_keywords):
                                print(f"[PRICING] Data in response from: {url[:60]}...")

                                # Try to extract pricing values
                                price_matches = re.findall(r'"(?:price|cost|rate)":\s*([\d.]+)', body)
                                if price_matches:
                                    print(f"   Prices found: {price_matches[:5]}")
                except:
                    pass

                break

    async def run(self, start_url: str = "https://ai.azure.com"):
        """Run the discovery session."""

        print("=" * 70)
        print("Azure AI Foundry API Discovery")
        print("=" * 70)
        print("""
Instructions:
1. The browser will open to Azure AI Foundry
2. Log in if prompted
3. Navigate to Model Catalog
4. Click on Marketplace models (Claude, Llama, Mistral)
5. Click "Deploy" to trigger pricing display
6. Press Ctrl+C when done to save results
        """)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,  # Always headed for manual navigation
                slow_mo=100,
            )

            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
            )

            page = await context.new_page()

            # Attach event handlers
            page.on('request', self.on_request)
            page.on('response', self.on_response)

            # Navigate to start URL
            print(f"\nNavigating to {start_url}...")
            await page.goto(start_url)

            print("\nNavigate the portal manually. Press Ctrl+C when done.\n")

            # Keep running until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n\nStopping capture...")

            await browser.close()

        return self.analyze_results()

    def analyze_results(self) -> dict:
        """Analyze captured requests for pricing APIs."""

        print("\n" + "=" * 70)
        print("ANALYSIS")
        print("=" * 70)

        print(f"\nTotal requests captured: {len(self.captured_requests)}")
        print(f"Interesting requests (with keywords): {len(self.interesting_requests)}")

        # Find the most promising pricing API candidates
        pricing_candidates = []
        for req in self.captured_requests:
            if req.response_body and any(kw in req.pricing_keywords_found for kw in ['price', 'pricing', 'cost']):
                pricing_candidates.append(req)

        print(f"Requests with pricing in response: {len(pricing_candidates)}")

        if pricing_candidates:
            print("\n" + "-" * 70)
            print("BEST CANDIDATES FOR PRICING API:")
            print("-" * 70)

            for req in pricing_candidates[:10]:
                print(f"\n{req.method} {req.url}")
                print(f"  Status: {req.status_code}")
                print(f"  Keywords: {', '.join(req.pricing_keywords_found)}")

                # Show pricing-related snippet from response
                if req.response_body:
                    # Find pricing context
                    body = req.response_body
                    for pattern in [r'"price[^"]*":\s*\{[^}]+\}', r'"cost[^"]*":\s*[\d.]+', r'"rate[^"]*":\s*[\d.]+']:
                        matches = re.findall(pattern, body, re.IGNORECASE)
                        if matches:
                            print(f"  Sample: {matches[0][:200]}")
                            break

        # Save all results
        output = {
            'captured_at': datetime.now().isoformat(),
            'total_requests': len(self.captured_requests),
            'interesting_requests': len(self.interesting_requests),
            'pricing_candidates': len(pricing_candidates),
            'candidate_urls': [req.url for req in pricing_candidates],
            'all_interesting': [asdict(req) for req in self.interesting_requests],
            'pricing_details': [asdict(req) for req in pricing_candidates],
        }

        output_file = 'api_discovery_results.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"\n\nFull results saved to {output_file}")

        # Generate curl commands for testing
        if pricing_candidates:
            print("\n" + "-" * 70)
            print("TEST COMMANDS:")
            print("-" * 70)

            for req in pricing_candidates[:3]:
                auth_header = req.request_headers.get('authorization', '')
                if auth_header:
                    # Truncate token for display
                    auth_display = auth_header[:50] + "..." if len(auth_header) > 50 else auth_header
                else:
                    auth_display = "[no auth]"

                print(f"\n# {req.url[:60]}...")
                print(f"curl -X {req.method} \\")
                print(f"  '{req.url}' \\")
                print(f"  -H 'Authorization: {auth_display}'")

        return output


async def main():
    parser = argparse.ArgumentParser(description='Discover Azure AI Foundry pricing API')
    parser.add_argument('--url', default='https://ai.azure.com', help='Starting URL')
    args = parser.parse_args()

    discovery = APIDiscovery()
    await discovery.run(args.url)


if __name__ == "__main__":
    asyncio.run(main())
