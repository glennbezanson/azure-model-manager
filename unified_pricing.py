#!/usr/bin/env python3
"""
Azure AI Foundry - Unified Model Pricing (Fully Dynamic)

Fetches live pricing from multiple sources in priority order:
1. Azure Marketplace API - Claude, Llama, Mistral, Cohere, AI21 (vendor-billed)
2. Azure Retail Prices API - GPT-4, embeddings, OpenAI models (Microsoft-billed)
3. LiteLLM community pricing - Dynamic fallback from GitHub-hosted JSON
4. Hardcoded fallback - Emergency last resort (rarely used)

Usage:
    from unified_pricing import get_model_pricing, PricingClient

    # Simple lookup
    pricing = get_model_pricing("claude-opus-4-5")
    print(f"${pricing.input_per_1m}/1M input, ${pricing.output_per_1m}/1M output")
    print(f"Source: {pricing.source.value}")

    # With client for batch operations
    client = PricingClient()
    for model in ["gpt-4o", "claude-sonnet-4-5", "llama-3-1-70b"]:
        p = client.get_pricing(model)
        print(f"{model}: {p.source.value}")
"""

import requests
import json
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from enum import Enum


class PricingSource(Enum):
    """Source of pricing data."""
    MARKETPLACE_API = "marketplace_api"
    RETAIL_API = "retail_api"
    LITELLM = "litellm"
    HARDCODED = "hardcoded"
    UNKNOWN = "unknown"


class BillingType(Enum):
    """How the model is billed."""
    MICROSOFT = "microsoft"      # Azure OpenAI / Cognitive Services
    MARKETPLACE = "marketplace"  # Third-party via Azure Marketplace
    UNKNOWN = "unknown"


@dataclass
class ModelPricing:
    """Pricing information for a model."""
    model_name: str
    publisher: str
    input_per_1m: Optional[float] = None
    output_per_1m: Optional[float] = None
    cache_write_per_1m: Optional[float] = None
    cache_hit_per_1m: Optional[float] = None
    source: PricingSource = PricingSource.UNKNOWN
    billing_type: BillingType = BillingType.UNKNOWN
    offer_id: Optional[str] = None
    region: Optional[str] = None
    unit: str = "1M tokens"
    notes: Optional[str] = None
    fetched_at: Optional[str] = None

    def estimate_cost(self, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """Estimate cost for given token counts."""
        cost = 0.0
        if self.input_per_1m and input_tokens:
            cost += (input_tokens / 1_000_000) * self.input_per_1m
        if self.output_per_1m and output_tokens:
            cost += (output_tokens / 1_000_000) * self.output_per_1m
        return cost

    def to_dict(self) -> dict:
        return {
            'model_name': self.model_name,
            'publisher': self.publisher,
            'input_per_1m': self.input_per_1m,
            'output_per_1m': self.output_per_1m,
            'cache_write_per_1m': self.cache_write_per_1m,
            'cache_hit_per_1m': self.cache_hit_per_1m,
            'source': self.source.value,
            'billing_type': self.billing_type.value,
            'offer_id': self.offer_id,
            'region': self.region,
            'notes': self.notes,
            'fetched_at': self.fetched_at,
        }


# =============================================================================
# MARKETPLACE OFFER ID MAPPINGS
# Pattern: {publisher}.{publisher}-{model-name}-offer
# =============================================================================

MARKETPLACE_OFFERS = {
    # =========================================================================
    # ANTHROPIC CLAUDE (Verified working via API discovery 2025-12-13)
    # Pattern: anthropic.anthropic-{model}-offer
    # =========================================================================
    "claude-opus-4-5": "anthropic.anthropic-claude-opus-4-5-offer",
    "claude-sonnet-4-5": "anthropic.anthropic-claude-sonnet-4-5-offer",
    "claude-haiku-4-5": "anthropic.anthropic-claude-haiku-4-5-offer",
    "claude-opus-4-1": "anthropic.anthropic-claude-opus-4-1-offer",
    # Note: Claude 3.x models do NOT have Marketplace offers - use LiteLLM fallback

    # =========================================================================
    # COHERE (Verified working via API discovery 2025-12-13)
    # Pattern: cohere.cohere-{model}-offer
    # Note: Dated versions work, generic names don't
    # =========================================================================
    "command-r-plus-08-2024": "cohere.cohere-command-r-plus-08-2024-offer",
    "cohere-command-r-plus-08-2024": "cohere.cohere-command-r-plus-08-2024-offer",
    "command-r-08-2024": "cohere.cohere-command-r-08-2024-offer",
    "cohere-command-r-08-2024": "cohere.cohere-command-r-08-2024-offer",
    "embed-v3-english": "cohere.cohere-embed-v3-english-offer",
    "cohere-embed-v3-english": "cohere.cohere-embed-v3-english-offer",
    "embed-v3-multilingual": "cohere.cohere-embed-v3-multilingual-offer",
    "cohere-embed-v3-multilingual": "cohere.cohere-embed-v3-multilingual-offer",

    # =========================================================================
    # AI21 LABS (Verified working via API discovery 2025-12-13)
    # Pattern: ai21labs.ai21-{model}-offer
    # =========================================================================
    "jamba-1-5-large": "ai21labs.ai21-jamba-1-5-large-offer",
    "ai21-jamba-1-5-large": "ai21labs.ai21-jamba-1-5-large-offer",
    "jamba-instruct": "ai21labs.ai21-jamba-instruct-offer",
    "ai21-jamba-instruct": "ai21labs.ai21-jamba-instruct-offer",

    # =========================================================================
    # NOT ON MARKETPLACE (use LiteLLM/Retail API fallback):
    # - Meta Llama: Deployed via Azure ML Managed Endpoints, not Marketplace
    # - Mistral: Deployed via Azure ML Managed Endpoints, not Marketplace
    # - Nvidia: Deployed via Azure ML Managed Endpoints, not Marketplace
    # - Claude 3.x: Older models not on Marketplace
    # =========================================================================
}

# =============================================================================
# RETAIL PRICES API MODEL PATTERNS
# Maps model names to meter name patterns in the Retail Prices API
# =============================================================================

RETAIL_MODEL_PATTERNS = {
    # =========================================================================
    # GPT-4O SERIES
    # =========================================================================
    "gpt-4o": ["gpt-4o input", "gpt-4o output", "gpt-4o-2024"],
    "gpt-4o-mini": ["gpt-4o-mini input", "gpt-4o-mini output", "gpt-4o-mini-2024"],
    "gpt-4o-realtime": ["gpt-4o-realtime", "gpt-4o realtime"],
    "gpt-4o-audio": ["gpt-4o-audio", "gpt-4o audio"],

    # =========================================================================
    # GPT-4.1 / GPT-4.5 SERIES
    # =========================================================================
    "gpt-4.1": ["gpt-4.1", "gpt-41"],
    "gpt-4.1-mini": ["gpt-4.1-mini", "gpt-41-mini"],
    "gpt-4.1-nano": ["gpt-4.1-nano", "gpt-41-nano"],
    "gpt-4.5-preview": ["gpt-4.5", "gpt-45"],

    # =========================================================================
    # GPT-4 SERIES
    # =========================================================================
    "gpt-4-turbo": ["gpt-4-turbo input", "gpt-4-turbo output", "gpt-4-turbo-2024"],
    "gpt-4-turbo-vision": ["gpt-4-turbo-vision", "gpt-4 turbo vision"],
    "gpt-4": ["gpt-4 input", "gpt-4 output"],
    "gpt-4-32k": ["gpt-4-32k input", "gpt-4-32k output"],
    "gpt-4-vision": ["gpt-4-vision", "gpt-4v"],

    # =========================================================================
    # GPT-3.5 SERIES
    # =========================================================================
    "gpt-35-turbo": ["gpt-35-turbo input", "gpt-35-turbo output", "gpt-3.5-turbo"],
    "gpt-35-turbo-16k": ["gpt-35-turbo-16k input", "gpt-35-turbo-16k output"],
    "gpt-35-turbo-instruct": ["gpt-35-turbo-instruct", "gpt-3.5-turbo-instruct"],

    # =========================================================================
    # O-SERIES (REASONING MODELS)
    # =========================================================================
    "o1": ["o1 input", "o1 output", "o1-2024"],
    "o1-mini": ["o1-mini input", "o1-mini output"],
    "o1-preview": ["o1-preview input", "o1-preview output"],
    "o1-pro": ["o1-pro input", "o1-pro output"],
    "o3": ["o3 input", "o3 output"],
    "o3-mini": ["o3-mini input", "o3-mini output"],
    "o4-mini": ["o4-mini input", "o4-mini output"],

    # =========================================================================
    # EMBEDDINGS
    # =========================================================================
    "text-embedding-3-small": ["text-embedding-3-small", "embedding-3-small"],
    "text-embedding-3-large": ["text-embedding-3-large", "embedding-3-large"],
    "text-embedding-ada-002": ["text-embedding-ada", "ada-002"],

    # =========================================================================
    # IMAGE / AUDIO / OTHER
    # =========================================================================
    "dall-e-3": ["dall-e-3", "dalle-3", "dall-e 3"],
    "dall-e-2": ["dall-e-2", "dalle-2", "dall-e 2"],
    "whisper": ["whisper"],
    "tts": ["tts standard", "text to speech"],
    "tts-hd": ["tts-hd", "tts hd"],

    # =========================================================================
    # FINE-TUNING
    # =========================================================================
    "gpt-4o-mini-fine-tuning": ["gpt-4o-mini fine-tun", "gpt-4o-mini finetun"],
    "gpt-35-turbo-fine-tuning": ["gpt-35-turbo fine-tun", "gpt-3.5-turbo finetun"],
    "davinci-002-fine-tuning": ["davinci-002 fine-tun"],
    "babbage-002-fine-tuning": ["babbage-002 fine-tun"],
}


# =============================================================================
# LITELLM COMMUNITY PRICING (dynamic fallback)
# Source: https://github.com/BerriAI/litellm
# =============================================================================

LITELLM_PRICING_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# Model name mappings: our names -> LiteLLM keys
# LiteLLM uses provider prefixes like "azure/gpt-4o", "anthropic/claude-opus-4-5"
LITELLM_MODEL_MAPPINGS = {
    # =========================================================================
    # CLAUDE MODELS (Current deployable only)
    # =========================================================================
    "claude-opus-4-5": ["anthropic/claude-opus-4-5", "claude-opus-4-5"],
    "claude-sonnet-4-5": ["anthropic/claude-sonnet-4-5", "claude-sonnet-4-5"],
    "claude-haiku-4-5": ["anthropic/claude-haiku-4-5", "claude-haiku-4-5"],
    "claude-opus-4-1": ["anthropic/claude-opus-4-1", "claude-opus-4-1"],

    # =========================================================================
    # OPENAI GPT MODELS (Current deployable)
    # =========================================================================
    "gpt-4o": ["azure/gpt-4o", "gpt-4o", "gpt-4o-2024-08-06", "gpt-4o-2024-11-20"],
    "gpt-4o-mini": ["azure/gpt-4o-mini", "gpt-4o-mini", "gpt-4o-mini-2024-07-18"],
    "gpt-4-turbo": ["azure/gpt-4-turbo", "gpt-4-turbo", "gpt-4-turbo-2024-04-09"],
    "gpt-4": ["azure/gpt-4", "gpt-4", "gpt-4-0613"],
    "gpt-35-turbo": ["azure/gpt-35-turbo", "gpt-3.5-turbo", "gpt-35-turbo"],
    "gpt-4.1": ["gpt-4.1", "gpt-4.1-2025-04-14"],
    "gpt-4.1-mini": ["gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"],
    "gpt-4.1-nano": ["gpt-4.1-nano", "gpt-4.1-nano-2025-04-14"],

    # =========================================================================
    # O-SERIES (REASONING)
    # =========================================================================
    "o1": ["o1", "o1-2024-12-17"],
    "o1-mini": ["o1-mini", "o1-mini-2024-09-12"],
    "o3-mini": ["o3-mini", "o3-mini-2025-01-31"],
    "o4-mini": ["o4-mini"],

    # =========================================================================
    # EMBEDDINGS
    # =========================================================================
    "text-embedding-3-small": ["azure/text-embedding-3-small", "text-embedding-3-small"],
    "text-embedding-3-large": ["azure/text-embedding-3-large", "text-embedding-3-large"],
    "text-embedding-ada-002": ["azure/text-embedding-ada-002", "text-embedding-ada-002"],

    # =========================================================================
    # MISTRAL (Current deployable)
    # =========================================================================
    "mistral-large": ["mistral/mistral-large-latest", "mistral-large-latest", "mistral/mistral-large-2411"],
    "mistral-large-2411": ["mistral/mistral-large-2411"],
    "mistral-small": ["mistral/mistral-small-latest", "mistral-small-latest"],
    "mistral-nemo": ["mistral/open-mistral-nemo", "mistral-nemo"],
    "codestral": ["mistral/codestral-latest", "codestral-latest"],
    "ministral-3b": ["mistral/ministral-3b-latest", "ministral-3b-2410"],
    "ministral-8b": ["mistral/ministral-8b-latest", "ministral-8b-2410"],
    "pixtral-12b": ["mistral/pixtral-12b-2409"],
    "pixtral-large": ["mistral/pixtral-large-latest", "mistral/pixtral-large-2411"],

    # =========================================================================
    # LLAMA (Current deployable)
    # =========================================================================
    "llama-3-3-70b-instruct": ["together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "llama-3-2-90b-vision-instruct": ["together_ai/meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo"],
    "llama-3-2-11b-vision-instruct": ["together_ai/meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo"],
    "llama-3-1-405b-instruct": ["together_ai/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo", "llama-3.1-405b"],
    "llama-3-1-70b-instruct": ["together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "llama-3.1-70b"],
    "llama-3-1-8b-instruct": ["together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "llama-3.1-8b"],

    # =========================================================================
    # COHERE (Current deployable)
    # =========================================================================
    "command-r-plus-08-2024": ["cohere/command-r-plus-08-2024", "cohere/command-r-plus"],
    "command-r-08-2024": ["cohere/command-r-08-2024", "cohere/command-r"],
    "cohere-embed-v3-english": ["cohere/embed-english-v3.0"],
    "cohere-embed-v3-multilingual": ["cohere/embed-multilingual-v3.0"],

    # =========================================================================
    # AI21 (Current deployable)
    # =========================================================================
    "jamba-1-5-large": ["ai21/jamba-1.5-large", "jamba-1.5-large"],
    "jamba-1-5-mini": ["ai21/jamba-1.5-mini", "jamba-1.5-mini"],
    "jamba-instruct": ["ai21/jamba-instruct"],
}


# =============================================================================
# HARDCODED FALLBACK PRICING (emergency last resort)
# Only used if both APIs AND LiteLLM fetch fail
# Last updated: 2025-12-13
# =============================================================================

# =============================================================================
# NO HARDCODED FALLBACK - All pricing is fetched dynamically
# =============================================================================
# Pricing sources (in priority order):
# 1. Marketplace API - for vendor models with known offer IDs (Claude, Cohere, AI21)
# 2. Retail Prices API - for Microsoft models (GPT, o-series, embeddings)
# 3. LiteLLM community data - for everything else (Llama, Mistral, etc.)
#
# If no source returns pricing, the model returns None (not stale hardcoded data)


class PricingClient:
    """
    Unified pricing client combining multiple data sources.

    Priority:
    1. Cache (if valid)
    2. Marketplace API (for vendor models: Claude, Llama, Mistral, etc.)
    3. Retail Prices API (for Microsoft models: GPT-4, embeddings, etc.)
    4. LiteLLM community pricing (dynamic fallback from GitHub)
    5. Hardcoded fallback (emergency last resort)
    """

    MARKETPLACE_API_URL = "https://marketplace.microsoft.com/view/appPricing"
    RETAIL_PRICES_URL = "https://prices.azure.com/api/retail/prices"

    def __init__(self, market: str = "us", cache_ttl_minutes: int = 60, timeout: int = 15):
        self.market = market
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.timeout = timeout
        self._cache: Dict[str, Tuple[ModelPricing, datetime]] = {}
        self._retail_prices_cache: Optional[List[dict]] = None
        self._retail_cache_time: Optional[datetime] = None
        self._litellm_cache: Optional[Dict] = None
        self._litellm_cache_time: Optional[datetime] = None

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _is_cache_valid(self, model_name: str) -> bool:
        """Check if cached pricing is still valid."""
        if model_name not in self._cache:
            return False
        _, cached_at = self._cache[model_name]
        return datetime.now() - cached_at < self.cache_ttl

    def _normalize_model_name(self, name: str) -> str:
        """Normalize model name for lookups."""
        normalized = name.lower().strip()
        # Common substitutions
        normalized = normalized.replace('_', '-')
        normalized = normalized.replace('gpt-3.5', 'gpt-35')
        return normalized

    def _get_publisher(self, model_name: str) -> str:
        """Determine publisher from model name."""
        name = model_name.lower()
        if any(x in name for x in ['claude', 'anthropic']):
            return 'anthropic'
        elif any(x in name for x in ['llama', 'meta']):
            return 'meta'
        elif any(x in name for x in ['mistral', 'codestral', 'ministral', 'pixtral']):
            return 'mistralai'
        elif any(x in name for x in ['cohere', 'command-r', 'embed-v3']):
            return 'cohere'
        elif any(x in name for x in ['jamba', 'ai21']):
            return 'ai21labs'
        elif any(x in name for x in ['gpt', 'dall-e', 'whisper', 'tts', 'o1', 'o3', 'o4', 'text-embedding']):
            return 'openai'
        return 'unknown'

    def _get_billing_type(self, model_name: str) -> BillingType:
        """Determine billing type from model name."""
        publisher = self._get_publisher(model_name)
        if publisher == 'openai':
            return BillingType.MICROSOFT
        elif publisher in ['anthropic', 'meta', 'mistralai', 'cohere', 'ai21labs']:
            return BillingType.MARKETPLACE
        return BillingType.UNKNOWN

    def _is_marketplace_model(self, model_name: str) -> bool:
        """Check if model is billed through Marketplace."""
        return self._get_billing_type(model_name) == BillingType.MARKETPLACE

    def _has_known_marketplace_offer(self, model_name: str) -> bool:
        """Check if we have a verified Marketplace offer ID for this model."""
        normalized = self._normalize_model_name(model_name)
        return normalized in MARKETPLACE_OFFERS

    # =========================================================================
    # MARKETPLACE API
    # =========================================================================

    def _get_offer_id(self, model_name: str) -> Optional[str]:
        """Get offer ID for a model."""
        normalized = self._normalize_model_name(model_name)

        # Direct lookup
        if normalized in MARKETPLACE_OFFERS:
            return MARKETPLACE_OFFERS[normalized]

        # Try without version suffix
        base = normalized.rsplit('-', 1)[0] if '-' in normalized else normalized
        if base in MARKETPLACE_OFFERS:
            return MARKETPLACE_OFFERS[base]

        # Try to construct offer ID
        publisher = self._get_publisher(model_name)
        if publisher and publisher != 'unknown':
            return f"{publisher}.{publisher}-{normalized}-offer"

        return None

    def _fetch_marketplace_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Fetch pricing from Azure Marketplace API."""
        offer_id = self._get_offer_id(model_name)
        if not offer_id:
            return None

        try:
            url = f"{self.MARKETPLACE_API_URL}/{offer_id}/{self.market}"
            response = requests.get(url, timeout=self.timeout)

            if response.status_code != 200:
                return None

            data = response.json()

            pricing = ModelPricing(
                model_name=model_name,
                publisher=self._get_publisher(model_name),
                source=PricingSource.MARKETPLACE_API,
                billing_type=BillingType.MARKETPLACE,
                offer_id=offer_id,
                fetched_at=datetime.now().isoformat(),
            )

            # Parse meters from response
            # Response structure: { "skus": [{ "termPrices": [{ "customMeter": [...] }] }] }
            meters = []
            if isinstance(data, dict) and 'skus' in data:
                for sku in data.get('skus', []):
                    for term in sku.get('termPrices', []):
                        meters.extend(term.get('customMeter', []))
            elif isinstance(data, list):
                meters = data
            elif isinstance(data, dict):
                # Fallback patterns
                meters = data.get('meters', data.get('pricingData', data.get('items', [])))
                if not meters and 'plans' in data:
                    for plan in data.get('plans', []):
                        meters.extend(plan.get('meters', []))

            # Track if we've found standard pricing (prefer over long-context)
            found_standard_input = False
            found_standard_output = False

            for meter in meters:
                # Response uses 'title' and 'rate' fields
                meter_name = str(meter.get('title', meter.get('meterName', meter.get('name', '')))).lower()
                price = meter.get('rate', meter.get('price', meter.get('unitPrice', 0)))

                if isinstance(price, dict):
                    price = price.get('amount', price.get('value', 0))

                try:
                    price_float = float(price)
                except (ValueError, TypeError):
                    continue

                # Skip long-context pricing if we already have standard
                is_long_context = 'long' in meter_name or '>128k' in meter_name or '128k+' in meter_name

                # API returns per 1K tokens, convert to per 1M
                price_per_1m = price_float * 1000

                # Classify meter
                if 'input' in meter_name or 'prompt' in meter_name:
                    if not found_standard_input or (not is_long_context):
                        pricing.input_per_1m = price_per_1m
                        if not is_long_context:
                            found_standard_input = True
                elif 'output' in meter_name or 'completion' in meter_name:
                    if not found_standard_output or (not is_long_context):
                        pricing.output_per_1m = price_per_1m
                        if not is_long_context:
                            found_standard_output = True
                elif 'cache' in meter_name and 'write' in meter_name and '1h' not in meter_name:
                    if not pricing.cache_write_per_1m:
                        pricing.cache_write_per_1m = price_per_1m
                elif 'cache' in meter_name and 'hit' in meter_name:
                    if not pricing.cache_hit_per_1m:
                        pricing.cache_hit_per_1m = price_per_1m

            return pricing if (pricing.input_per_1m or pricing.output_per_1m) else None

        except Exception as e:
            print(f"Marketplace API error for {model_name}: {e}")
            return None

    # =========================================================================
    # RETAIL PRICES API
    # =========================================================================

    def _fetch_retail_prices_data(self) -> List[dict]:
        """Fetch and cache retail prices data."""
        # Check if cache is valid
        if (self._retail_prices_cache is not None and
            self._retail_cache_time is not None and
            datetime.now() - self._retail_cache_time < self.cache_ttl):
            return self._retail_prices_cache

        all_items = []

        try:
            # Query for AI + Machine Learning services
            filters = [
                "serviceName eq 'Azure OpenAI Service'",
                "serviceName eq 'Foundry Models'",
                "serviceName eq 'Cognitive Services'",
            ]

            for filter_query in filters:
                url = f"{self.RETAIL_PRICES_URL}?$filter={filter_query}"

                while url:
                    response = requests.get(url, timeout=self.timeout)
                    if response.status_code != 200:
                        break

                    data = response.json()
                    items = data.get('Items', [])
                    all_items.extend(items)

                    # Handle pagination
                    url = data.get('NextPageLink')

                    # Limit pagination to avoid huge fetches
                    if len(all_items) > 5000:
                        break

            self._retail_prices_cache = all_items
            self._retail_cache_time = datetime.now()

        except Exception as e:
            print(f"Retail Prices API error: {e}")

        return self._retail_prices_cache or []

    def _fetch_retail_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Fetch pricing from Azure Retail Prices API."""
        normalized = self._normalize_model_name(model_name)

        # Get patterns to match
        patterns = RETAIL_MODEL_PATTERNS.get(normalized, [normalized])

        # Fetch all retail prices
        items = self._fetch_retail_prices_data()
        if not items:
            return None

        pricing = ModelPricing(
            model_name=model_name,
            publisher='openai',
            source=PricingSource.RETAIL_API,
            billing_type=BillingType.MICROSOFT,
            fetched_at=datetime.now().isoformat(),
        )

        # Find matching meters
        for item in items:
            meter_name = item.get('meterName', '').lower()
            product_name = item.get('productName', '').lower()
            sku_name = item.get('skuName', '').lower()

            # Check if any pattern matches
            matched = False
            for pattern in patterns:
                if pattern.lower() in meter_name or pattern.lower() in product_name:
                    matched = True
                    break

            if not matched:
                continue

            # Skip non-consumption (reservations, etc.)
            price_type = item.get('type', '')
            if price_type and 'Consumption' not in price_type:
                continue

            price = item.get('retailPrice', 0)
            unit = item.get('unitOfMeasure', '')

            # Convert to per 1M tokens
            if '1K' in unit:
                price_per_1m = price * 1000
            elif '1M' in unit:
                price_per_1m = price
            elif '1 Hour' in unit:
                continue  # Skip hourly rates
            else:
                price_per_1m = price * 1000  # Assume 1K if not specified

            # Classify by meter name
            if 'input' in meter_name or 'prompt' in meter_name:
                if not pricing.input_per_1m:
                    pricing.input_per_1m = price_per_1m
                    pricing.region = item.get('armRegionName')
            elif 'output' in meter_name or 'completion' in meter_name or 'generated' in meter_name:
                if not pricing.output_per_1m:
                    pricing.output_per_1m = price_per_1m

        return pricing if (pricing.input_per_1m or pricing.output_per_1m) else None

    # =========================================================================
    # LITELLM COMMUNITY PRICING (dynamic fallback)
    # =========================================================================

    def _fetch_litellm_data(self) -> Optional[Dict]:
        """Fetch and cache LiteLLM community pricing data."""
        # Check if cache is valid
        if (self._litellm_cache is not None and
            self._litellm_cache_time is not None and
            datetime.now() - self._litellm_cache_time < self.cache_ttl):
            return self._litellm_cache

        try:
            response = requests.get(LITELLM_PRICING_URL, timeout=self.timeout)
            if response.status_code == 200:
                self._litellm_cache = response.json()
                self._litellm_cache_time = datetime.now()
                return self._litellm_cache
        except Exception as e:
            print(f"LiteLLM pricing fetch error: {e}")

        return self._litellm_cache  # Return stale cache if fetch fails

    def _get_litellm_pricing(self, model_name: str) -> Optional[ModelPricing]:
        """Get pricing from LiteLLM community data."""
        data = self._fetch_litellm_data()
        if not data:
            return None

        normalized = self._normalize_model_name(model_name)

        # Get candidate keys to try
        candidates = LITELLM_MODEL_MAPPINGS.get(normalized, [normalized])

        # Also try common variations
        candidates.extend([
            normalized,
            f"azure/{normalized}",
            f"anthropic/{normalized}",
            f"openai/{normalized}",
            normalized.replace('-', '.'),
            normalized.replace('-', '_'),
        ])

        # Try each candidate
        for key in candidates:
            if key in data:
                model_data = data[key]

                # LiteLLM stores prices per token, we need per 1M
                input_cost = model_data.get('input_cost_per_token')
                output_cost = model_data.get('output_cost_per_token')

                # Convert to per 1M tokens
                input_per_1m = input_cost * 1_000_000 if input_cost else None
                output_per_1m = output_cost * 1_000_000 if output_cost else None

                if input_per_1m or output_per_1m:
                    return ModelPricing(
                        model_name=model_name,
                        publisher=self._get_publisher(model_name),
                        input_per_1m=input_per_1m,
                        output_per_1m=output_per_1m,
                        source=PricingSource.LITELLM,
                        billing_type=self._get_billing_type(model_name),
                        notes=f"LiteLLM community data (key: {key})",
                        fetched_at=datetime.now().isoformat(),
                    )

        return None

    # =========================================================================
    # MAIN API
    # =========================================================================

    def get_pricing(self, model_name: str, use_cache: bool = True) -> Optional[ModelPricing]:
        """
        Get pricing for a model - FULLY DYNAMIC, no hardcoded fallback.

        Routing logic:
        - Marketplace models (Claude, Cohere, AI21) with known offer IDs:
          1. Marketplace API
          2. LiteLLM community data

        - Marketplace models without known offers (Llama, Mistral):
          1. LiteLLM community data (skip Marketplace API to save time)

        - Microsoft models (GPT, o-series, embeddings):
          1. Retail Prices API
          2. LiteLLM community data

        Returns None if no API returns pricing (no stale hardcoded data).
        """
        normalized = self._normalize_model_name(model_name)

        # Check cache
        if use_cache and self._is_cache_valid(normalized):
            return self._cache[normalized][0]

        pricing = None

        # Route to appropriate API based on billing type and known offers
        if self._is_marketplace_model(model_name):
            # Only try Marketplace API if we have a verified offer ID
            if self._has_known_marketplace_offer(model_name):
                pricing = self._fetch_marketplace_pricing(model_name)

            # If no Marketplace pricing, try LiteLLM (skip Retail for vendor models)
            if not pricing:
                pricing = self._get_litellm_pricing(model_name)
        else:
            # Try Retail API first for Microsoft models
            pricing = self._fetch_retail_pricing(model_name)
            if not pricing:
                # Fallback to LiteLLM
                pricing = self._get_litellm_pricing(model_name)

        # Cache result (even None to avoid repeated failed lookups)
        if pricing:
            self._cache[normalized] = (pricing, datetime.now())

        return pricing

    def clear_cache(self):
        """Clear all caches."""
        self._cache.clear()
        self._retail_prices_cache = None
        self._retail_cache_time = None
        self._litellm_cache = None
        self._litellm_cache_time = None

    def get_all_pricing(self, models: List[str]) -> Dict[str, ModelPricing]:
        """Get pricing for multiple models."""
        results = {}
        for model in models:
            pricing = self.get_pricing(model)
            if pricing:
                results[model] = pricing
        return results

    def get_all_known_models(self) -> List[str]:
        """Get list of all known model names from all sources."""
        models = set()

        # From Marketplace offers (verified working offer IDs)
        models.update(MARKETPLACE_OFFERS.keys())

        # From LiteLLM mappings
        models.update(LITELLM_MODEL_MAPPINGS.keys())

        # From Retail API patterns (Microsoft models)
        models.update(RETAIL_MODEL_PATTERNS.keys())

        return sorted(models)

    def fetch_all_pricing(self, include_litellm_discovery: bool = True) -> Dict[str, ModelPricing]:
        """
        Fetch pricing for ALL known models.

        Args:
            include_litellm_discovery: If True, also scan LiteLLM data for
                                       additional models not in our mappings

        Returns:
            Dict mapping model names to ModelPricing objects
        """
        results = {}

        # First, fetch all models we have mappings for
        known_models = self.get_all_known_models()
        print(f"Fetching pricing for {len(known_models)} known models...")

        for model in known_models:
            pricing = self.get_pricing(model)
            if pricing:
                results[model] = pricing

        # Optionally discover additional models from LiteLLM
        if include_litellm_discovery:
            litellm_data = self._fetch_litellm_data()
            if litellm_data:
                # Find models in LiteLLM we don't already have
                for key in litellm_data.keys():
                    # Skip if we already have this model
                    normalized = self._normalize_model_name(key)
                    if normalized in results:
                        continue

                    # Skip provider-prefixed duplicates we likely already have
                    if '/' in key:
                        base_name = key.split('/')[-1]
                        if base_name in results or self._normalize_model_name(base_name) in results:
                            continue

                    # Try to get pricing for this model
                    model_data = litellm_data[key]
                    input_cost = model_data.get('input_cost_per_token')
                    output_cost = model_data.get('output_cost_per_token')

                    if input_cost or output_cost:
                        input_per_1m = input_cost * 1_000_000 if input_cost else None
                        output_per_1m = output_cost * 1_000_000 if output_cost else None

                        results[key] = ModelPricing(
                            model_name=key,
                            publisher=self._get_publisher(key),
                            input_per_1m=input_per_1m,
                            output_per_1m=output_per_1m,
                            source=PricingSource.LITELLM,
                            billing_type=self._get_billing_type(key),
                            notes=f"LiteLLM discovery",
                            fetched_at=datetime.now().isoformat(),
                        )

        return results

    def export_all_pricing(self, filepath: str = None, include_litellm_discovery: bool = True) -> dict:
        """
        Export all pricing to a JSON structure.

        Args:
            filepath: Optional path to save JSON file
            include_litellm_discovery: Include models discovered from LiteLLM

        Returns:
            Dict with pricing data and metadata
        """
        all_pricing = self.fetch_all_pricing(include_litellm_discovery)

        # Build export structure
        export = {
            "generated_at": datetime.now().isoformat(),
            "sources_priority": ["marketplace_api", "retail_api", "litellm"],
            "models": [p.to_dict() for p in all_pricing.values()],
            "summary": {
                "total_models": len(all_pricing),
                "by_source": {},
                "by_publisher": {},
                "by_billing_type": {},
            }
        }

        # Calculate summaries
        for pricing in all_pricing.values():
            # By source
            source = pricing.source.value
            export["summary"]["by_source"][source] = export["summary"]["by_source"].get(source, 0) + 1

            # By publisher
            pub = pricing.publisher
            export["summary"]["by_publisher"][pub] = export["summary"]["by_publisher"].get(pub, 0) + 1

            # By billing type
            billing = pricing.billing_type.value
            export["summary"]["by_billing_type"][billing] = export["summary"]["by_billing_type"].get(billing, 0) + 1

        # Sort models by publisher then name
        export["models"].sort(key=lambda x: (x.get("publisher", ""), x.get("model_name", "")))

        if filepath:
            with open(filepath, 'w') as f:
                json.dump(export, f, indent=2)
            print(f"Exported {len(all_pricing)} models to {filepath}")

        return export


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_default_client: Optional[PricingClient] = None


def get_client() -> PricingClient:
    """Get or create the default pricing client."""
    global _default_client
    if _default_client is None:
        _default_client = PricingClient()
    return _default_client


def get_model_pricing(model_name: str) -> Optional[ModelPricing]:
    """Get pricing for a model using the default client."""
    return get_client().get_pricing(model_name)


def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Estimate cost for a model given token counts."""
    pricing = get_model_pricing(model_name)
    if pricing:
        return pricing.estimate_cost(input_tokens, output_tokens)
    return None


def estimate_monthly_cost(
    model_name: str,
    daily_input_tokens: int,
    daily_output_tokens: int,
    days: int = 30,
) -> dict:
    """Estimate monthly cost for a model."""
    pricing = get_model_pricing(model_name)

    total_input = daily_input_tokens * days
    total_output = daily_output_tokens * days

    result = {
        'model': model_name,
        'input_tokens': total_input,
        'output_tokens': total_output,
        'cost': None,
        'source': None,
        'billing_type': None,
    }

    if pricing:
        result['cost'] = pricing.estimate_cost(total_input, total_output)
        result['source'] = pricing.source.value
        result['billing_type'] = pricing.billing_type.value

    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    import sys

    print("Azure AI Foundry - Unified Pricing Client")
    print("=" * 70)
    print("Priority: Marketplace API > Retail API > LiteLLM > Hardcoded")
    print()

    client = PricingClient()

    # Check for --all flag
    if "--all" in sys.argv or "-a" in sys.argv:
        print("Fetching ALL known models...")
        print()

        # Determine output file
        output_file = None
        for i, arg in enumerate(sys.argv):
            if arg in ["--output", "-o"] and i + 1 < len(sys.argv):
                output_file = sys.argv[i + 1]
                break

        if not output_file:
            output_file = "all_pricing.json"

        # Fetch and export (Azure models only, not every provider in LiteLLM)
        export = client.export_all_pricing(output_file, include_litellm_discovery=False)

        print()
        print("=" * 70)
        print(f"Total models: {export['summary']['total_models']}")
        print()
        print("By source:")
        for source, count in sorted(export['summary']['by_source'].items()):
            print(f"  {source}: {count}")
        print()
        print("By publisher:")
        for pub, count in sorted(export['summary']['by_publisher'].items()):
            print(f"  {pub}: {count}")
        print()
        print(f"Results saved to: {output_file}")
        return

    # Default: show sample models
    test_models = [
        # Marketplace models (vendor billing) - CURRENT DEPLOYABLE ONLY
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-1",
        "mistral-large",
        "mistral-small",
        "llama-3-3-70b-instruct",
        "llama-3-1-405b-instruct",
        "llama-3-1-70b-instruct",
        "command-r-plus-08-2024",
        "jamba-1-5-large",
        # Microsoft models (Azure billing)
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-35-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
        "text-embedding-3-small",
    ]

    print(f"{'Model':<30} {'Input/1M':<12} {'Output/1M':<12} {'Source':<18} {'Billing':<12}")
    print("-" * 90)

    for model in test_models:
        pricing = client.get_pricing(model)
        if pricing:
            input_p = f"${pricing.input_per_1m:.2f}" if pricing.input_per_1m else "-"
            output_p = f"${pricing.output_per_1m:.2f}" if pricing.output_per_1m else "-"
            print(f"{model:<30} {input_p:<12} {output_p:<12} {pricing.source.value:<18} {pricing.billing_type.value:<12}")
        else:
            print(f"{model:<30} {'N/A':<12} {'N/A':<12} {'not found':<18}")

    print()
    print("TIP: Run with --all to fetch pricing for ALL known models")
    print("     python unified_pricing.py --all --output pricing.json")


if __name__ == "__main__":
    main()
