# Azure AI Model Pricing API Research

## Summary

**UPDATE: Marketplace Pricing API DISCOVERED!**

After extensive investigation, we found a **working API** that exposes Marketplace AI model pricing:

```
GET https://marketplace.microsoft.com/view/appPricing/{offer-id}/{market}
```

This API returns detailed per-token pricing for all Marketplace models including Claude, Llama, Mistral, etc.

---

## DISCOVERED: Marketplace Pricing API

### Endpoint
```
GET https://marketplace.microsoft.com/view/appPricing/{publisher}.{offer-name}/us
```

### Access
- **Public** (no authentication required)
- Returns JSON with detailed meter pricing

### Offer ID Pattern
The offer ID follows the pattern: `{publisher}.{publisher}-{model-name}-offer`

Examples:
- Claude Opus 4.5: `anthropic.anthropic-claude-opus-4-5-offer`
- Claude Sonnet 4.5: `anthropic.anthropic-claude-sonnet-4-5-offer`
- Claude Haiku 4.5: `anthropic.anthropic-claude-haiku-4-5-offer`

### Sample Request
```bash
curl "https://marketplace.microsoft.com/view/appPricing/anthropic.anthropic-claude-opus-4-5-offer/us"
```

### Claude Model Pricing (Retrieved via API)

#### Claude Opus 4.5
| Meter | Price per 1K tokens |
|-------|---------------------|
| Input tokens | $0.005 |
| Output tokens | $0.025 |
| Cache write tokens | $0.00625 |
| Cache write (1h) tokens | $0.01 |
| Cache hit tokens | $0.0005 |

#### Claude Sonnet 4.5
| Meter | Standard | Long Context (>128K) |
|-------|----------|---------------------|
| Input tokens | $0.003 | $0.006 |
| Output tokens | $0.015 | $0.0225 |
| Cache write tokens | $0.00375 | $0.0075 |
| Cache write (1h) tokens | $0.006 | $0.012 |
| Cache hit tokens | $0.0003 | $0.0006 |

#### Claude Haiku 4.5
| Meter | Price per 1K tokens |
|-------|---------------------|
| Input tokens | $0.001 |
| Output tokens | $0.005 |
| Cache write tokens | $0.00125 |
| Cache write (1h) tokens | $0.002 |
| Cache hit tokens | $0.0001 |

### How We Found It
1. Navigated to Azure AI Foundry Model Catalog
2. Clicked on a model's pricing link (e.g., `https://aka.ms/claude-opus-4-5-plan-pricing`)
3. Captured network traffic on the Marketplace page
4. Found the API call: `GET /view/appPricing/{offer-id}/{market}`

### Additional Marketplace APIs
| Endpoint | Purpose |
|----------|---------|
| `/view/appPricing/{offer-id}/{market}` | Current pricing |
| `/view/appFuturePricing/{offer-id}/{market}` | Upcoming pricing changes |
| `catalogapi.azure.com/products?$expand=startingPrice` | Starting price summaries |

---

## Previous Research (Before Discovery)

The following APIs were investigated but do NOT expose Marketplace pricing:

---

## APIs Investigated

### 1. Azure Retail Prices API
**Endpoint:** `https://prices.azure.com/api/retail/prices`

**Access:** Public (no authentication required)

**Findings:**
- Service filter `serviceName eq 'Azure OpenAI'` returns **0 results**
- Working service names found:
  - `Foundry Models`
  - `Cognitive Services`
  - `Azure Machine Learning`
- Service family `AI + Machine Learning` contains pricing data
- **Does NOT include** Marketplace vendor models (Claude, Llama, Mistral)
- Only covers Microsoft-billed services (GPT-4, embeddings, etc.)

**Sample Query:**
```bash
curl "https://prices.azure.com/api/retail/prices?\$filter=serviceFamily eq 'AI + Machine Learning'"
```

### 2. ARM Model Catalog API
**Endpoint:** `GET /subscriptions/{sub}/providers/Microsoft.CognitiveServices/locations/{loc}/models`

**Access:** Requires Azure authentication

**Findings:**
- Returns **334 models** with metadata including:
  - Model name, version, format, publisher
  - Lifecycle status (GA, Preview, Deprecated)
  - Capabilities (chat, completion, embeddings, vision, function calling)
  - SKU names and capacity limits
- **SKU `cost[]` arrays are EMPTY** - no `meter_id` data exposed
- Hypothesis that `meter_id` could bridge to Retail Prices API was **disproven**

**Useful Fields:**
| Field | Example Value | Notes |
|-------|---------------|-------|
| `model.name` | `claude-3-5-sonnet` | Model identifier |
| `model.publisher` | `anthropic` | Vendor name |
| `skus[].name` | `GlobalProvisionedManaged` | Deployment SKU |
| `skus[].usage_name` | `OpenAI.Standard.gpt-4-turbo` | Potential name-matching key |
| `skus[].capacity` | `{min: 50, max: 1000, step: 50}` | TPM limits |
| `skus[].cost` | `[]` | **Always empty** |

### 3. Azure Commerce APIs
**Endpoints:**
- Rate Card: `GET /subscriptions/{sub}/providers/Microsoft.Commerce/RateCard`
- Usage Aggregates: `GET /subscriptions/{sub}/providers/Microsoft.Commerce/UsageAggregates`

**Findings:**
- Rate Card returns Microsoft-only pricing
- Usage Aggregates only shows post-consumption data
- Neither exposes Marketplace model pricing

### 4. Azure Cost Management API
**Endpoint:** `GET /subscriptions/{sub}/providers/Microsoft.CostManagement/query`

**Findings:**
- Only returns **historical consumption** data
- Cannot provide prospective/list pricing
- Useful for tracking actual spend, not price discovery

### 5. Azure Marketplace Catalog API
**Endpoint:** `https://catalogapi.azure.com/offers`

**Findings:**
- Returns offer metadata (descriptions, terms, publishers)
- **Does NOT expose pricing** for SaaS/pay-as-you-go models
- Pricing visibility requires navigating to publisher's pricing page

### 6. Machine Learning Workspace API
**Endpoint:** `GET /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{ws}/models`

**Findings:**
- Lists models deployed to ML workspace
- No pricing information included
- Primarily for model management, not cost discovery

---

## Why No API Exists

1. **Marketplace = Pass-Through Billing**
   - Azure acts as billing intermediary for vendor models
   - Vendors (Anthropic, Meta, Mistral) set their own pricing
   - Pricing is dynamic and vendor-controlled

2. **No Public Price Sheet**
   - Unlike Azure-native services, Marketplace pricing isn't published in Azure's price sheets
   - Each vendor maintains their own pricing documentation

3. **Consumption-Based Discovery Only**
   - Pricing appears in `meterId` on invoices after usage
   - No way to query prospective rates programmatically

---

## Recommended Approach

### Option 1: Use Marketplace Pricing API (Preferred)

Now that we've discovered the Marketplace Pricing API, you can fetch pricing programmatically:

```python
import requests

def get_marketplace_pricing(offer_id: str, market: str = "us") -> dict:
    """Fetch pricing from Azure Marketplace API."""
    url = f"https://marketplace.microsoft.com/view/appPricing/{offer_id}/{market}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

# Example usage
pricing = get_marketplace_pricing("anthropic.anthropic-claude-opus-4-5-offer")
```

### Option 2: Hardcoded Pricing Table (Fallback)

For models where the offer ID is unknown, maintain a static pricing table:

```python
MARKETPLACE_PRICING = {
    "claude-3-5-sonnet": {
        "publisher": "anthropic",
        "input_per_1m_tokens": 3.00,
        "output_per_1m_tokens": 15.00,
        "pricing_page": "https://www.anthropic.com/pricing",
        "last_updated": "2024-12-01"
    },
    "claude-3-5-haiku": {
        "publisher": "anthropic",
        "input_per_1m_tokens": 0.80,
        "output_per_1m_tokens": 4.00,
        "pricing_page": "https://www.anthropic.com/pricing",
        "last_updated": "2024-12-01"
    },
    "claude-opus-4-5": {
        "publisher": "anthropic",
        "input_per_1m_tokens": 15.00,
        "output_per_1m_tokens": 75.00,
        "pricing_page": "https://www.anthropic.com/pricing",
        "last_updated": "2024-12-01"
    },
    "llama-3-1-405b-instruct": {
        "publisher": "meta",
        "input_per_1m_tokens": 5.33,
        "output_per_1m_tokens": 16.00,
        "pricing_page": "https://azure.microsoft.com/en-us/pricing/details/machine-learning/",
        "last_updated": "2024-12-01"
    },
    "mistral-large-2407": {
        "publisher": "mistralai",
        "input_per_1m_tokens": 2.00,
        "output_per_1m_tokens": 6.00,
        "pricing_page": "https://azure.microsoft.com/en-us/pricing/details/mistral/",
        "last_updated": "2024-12-01"
    }
}
```

### Data Sources for Manual Updates

| Publisher | Pricing Documentation |
|-----------|----------------------|
| Anthropic | https://www.anthropic.com/pricing |
| OpenAI | https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/ |
| Meta (Llama) | https://azure.microsoft.com/en-us/pricing/details/machine-learning/ |
| Mistral | https://azure.microsoft.com/en-us/pricing/details/mistral/ |
| Cohere | https://azure.microsoft.com/en-us/pricing/details/cohere/ |

### Hybrid Approach

1. **Model Catalog API** - Get available models, capabilities, lifecycle status
2. **Hardcoded Pricing Table** - Provide cost estimates
3. **Cost Management API** - Track actual spend after deployment

---

## Scripts Created During Research

| Script | Purpose |
|--------|---------|
| `azure_pricing_dump.py` | Raw dump of Model Catalog + Retail Prices |
| `azure_pricing_explorer.py` | Meter ID bridge analysis |
| `discover_ai_services.py` | Service name discovery in Retail Prices |
| `azure_foundry_pricing.py` | ML workspace and SaaS resource queries |
| `azure_marketplace_pricing.py` | Marketplace catalog exploration |
| `discover_pricing_api.py` | **KEY**: Playwright script that captures network traffic to discover APIs |

---

## Key Learnings

1. **Service Name Mismatch**: "Azure OpenAI" filter returns nothing; use "Foundry Models" or "Cognitive Services"

2. **Empty Cost Arrays**: Model Catalog SKUs have `cost[]` arrays but they're always empty - no meter_id exposed

3. **Meter ID Bridge Disproven**: Cannot join Model Catalog to Retail Prices via meter_id

4. **Post-Consumption Only**: Marketplace pricing only appears after usage on invoices

5. **Windows Encoding Fix**: Python scripts printing to Windows console need:
   ```python
   import sys, io
   if sys.platform == 'win32':
       sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
   ```

---

## Future Considerations

- **Azure Advisor API**: May provide cost recommendations but not list prices
- **Partner Center API**: For CSP partners, may have pricing access
- **Vendor APIs**: Anthropic/Meta/Mistral may expose their own pricing APIs
- **Web Scraping**: Last resort for pricing pages (brittle, terms of service concerns)

---

*Research conducted: December 2024*
*Subscription: YOUR_SUBSCRIPTION_ID (Production)*
*Location: eastus*

---

## Appendix: Known Offer IDs

| Model | Offer ID |
|-------|----------|
| Claude Opus 4.5 | `anthropic.anthropic-claude-opus-4-5-offer` |
| Claude Sonnet 4.5 | `anthropic.anthropic-claude-sonnet-4-5-offer` |
| Claude Haiku 4.5 | `anthropic.anthropic-claude-haiku-4-5-offer` |

To find more offer IDs:
1. Go to https://ai.azure.com/catalog/models
2. Click on a model
3. Find the pricing link (e.g., `https://aka.ms/{model}-plan-pricing`)
4. Follow the redirect to get the full Marketplace URL
5. Extract the offer ID from: `marketplace.microsoft.com/.../product/saas/{offer-id}`
