"""Service for fetching models from Azure AI model catalog."""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.core.exceptions import HttpResponseError

from services.azure_auth import AzureAuthService
from services.config_manager import ConfigManager
from models.catalog_model import CatalogModel

logger = logging.getLogger(__name__)


class ModelCatalogService:
    """Service for fetching and caching Azure AI model catalog."""

    # Cache duration in seconds
    CACHE_DURATION = 300  # 5 minutes

    def __init__(self, config: ConfigManager, auth_service: AzureAuthService):
        """
        Initialize the model catalog service.

        Args:
            config: Configuration manager instance
            auth_service: Azure authentication service instance
        """
        self.config = config
        self.auth_service = auth_service
        self._client: Optional[CognitiveServicesManagementClient] = None
        self._cache: List[CatalogModel] = []
        self._cache_time: Optional[datetime] = None

    @property
    def client(self) -> CognitiveServicesManagementClient:
        """Get or create the Cognitive Services management client."""
        if self._client is None:
            self._client = CognitiveServicesManagementClient(
                credential=self.auth_service.credential,
                subscription_id=self.config.subscription_id
            )
        return self._client

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        if not self._cache or self._cache_time is None:
            return False
        return datetime.now() - self._cache_time < timedelta(seconds=self.CACHE_DURATION)

    def clear_cache(self) -> None:
        """Clear the model cache."""
        self._cache = []
        self._cache_time = None
        logger.info("Model cache cleared")

    def get_available_models(self, force_refresh: bool = False) -> List[CatalogModel]:
        """
        Get available models from the Azure AI model catalog.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of CatalogModel objects
        """
        if not force_refresh and self._is_cache_valid():
            logger.debug("Returning cached models")
            return self._cache

        try:
            models = self._fetch_models_from_azure()
            self._cache = models
            self._cache_time = datetime.now()
            logger.info(f"Fetched {len(models)} models from Azure")
            return models
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            # Return cached data if available, even if expired
            if self._cache:
                logger.warning("Returning stale cached data due to error")
                return self._cache
            raise

    def _fetch_models_from_azure(self) -> List[CatalogModel]:
        """Fetch models from Azure API."""
        models = []

        try:
            # Get models available in the specified location
            model_list = self.client.models.list(
                location=self.config.location
            )

            for model_data in model_list:
                try:
                    catalog_model = self._parse_model(model_data)
                    if catalog_model:
                        models.append(catalog_model)
                except Exception as e:
                    logger.warning(f"Failed to parse model: {e}")
                    continue

        except HttpResponseError as e:
            logger.error(f"Azure API error: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            raise

        # Sort by name
        models.sort(key=lambda m: m.name.lower())
        return models

    def _parse_model(self, model_data: Any) -> Optional[CatalogModel]:
        """
        Parse Azure model data into a CatalogModel.

        Args:
            model_data: Model data from Azure API

        Returns:
            CatalogModel instance or None if parsing fails
        """
        try:
            # Handle SDK response object
            if hasattr(model_data, 'model'):
                model_info = model_data.model
                name = model_info.name if model_info else ""
                version = model_info.version if model_info else ""
                model_format = model_info.format if model_info else "OpenAI"

                # Publisher is often None in Azure API, use format field instead
                # Format contains publisher name like "Anthropic", "OpenAI", etc.
                publisher = getattr(model_info, 'publisher', None)
                if not publisher or publisher == 'None':
                    # Format field typically contains the publisher/provider name
                    publisher = model_format if model_format else "Unknown"
            else:
                # Handle dict response
                model_info = model_data.get('model', {})
                name = model_info.get('name', '')
                version = model_info.get('version', '')
                model_format = model_info.get('format', 'OpenAI')
                publisher = model_info.get('publisher', 'OpenAI')

            if not name:
                return None

            # Extract capabilities
            capabilities = self._extract_capabilities(model_data)

            # Extract other properties
            if hasattr(model_data, 'model'):
                deprecation = getattr(model_info, 'deprecation', None)
                deprecation_date = deprecation.fine_tune if deprecation else None
                max_capacity = getattr(model_info, 'max_capacity', None)
                # SKUs are on model_info, not model_data
                skus = getattr(model_info, 'skus', [])
                sku_list = [s.name for s in skus] if skus else []
            else:
                deprecation_date = model_data.get('deprecation', {}).get('fineTune')
                max_capacity = model_data.get('maxCapacity')
                skus = model_data.get('skus', [])
                sku_list = [s.get('name', '') for s in skus] if skus else []

            # Get description from config or generate a default
            description = self.config.get_model_description(name)
            if not description:
                description = self._generate_description(name, capabilities)

            return CatalogModel(
                name=name,
                version=version,
                publisher=publisher,
                description=description,
                capabilities=capabilities,
                context_window=self._get_context_window(name),
                max_output_tokens=self._get_max_output(name),
                deprecation_date=deprecation_date,
                available_skus=sku_list,
                regions=[self.config.location],
                model_format=model_format
            )

        except Exception as e:
            logger.error(f"Error parsing model data: {e}")
            return None

    def _extract_capabilities(self, model_data: Any) -> List[str]:
        """Extract capabilities from model data."""
        capabilities = []

        # Check for capabilities object
        if hasattr(model_data, 'capabilities'):
            caps = model_data.capabilities
            if caps:
                if getattr(caps, 'chat_completion', False):
                    capabilities.append("chat")
                if getattr(caps, 'completion', False):
                    capabilities.append("completion")
                if getattr(caps, 'embeddings', False):
                    capabilities.append("embeddings")
                if getattr(caps, 'image_generation', False):
                    capabilities.append("image_generation")
                if getattr(caps, 'vision', False):
                    capabilities.append("vision")
                if getattr(caps, 'function_calling', False):
                    capabilities.append("function_calling")
                if getattr(caps, 'json_mode', False):
                    capabilities.append("json_mode")
        elif isinstance(model_data, dict):
            caps = model_data.get('capabilities', {})
            if caps.get('chatCompletion'):
                capabilities.append("chat")
            if caps.get('completion'):
                capabilities.append("completion")
            if caps.get('embeddings'):
                capabilities.append("embeddings")
            if caps.get('imageGeneration'):
                capabilities.append("image_generation")
            if caps.get('vision'):
                capabilities.append("vision")
            if caps.get('functionCalling'):
                capabilities.append("function_calling")
            if caps.get('jsonMode'):
                capabilities.append("json_mode")

        # Infer capabilities from model name if none detected
        if not capabilities:
            capabilities = self._infer_capabilities_from_name(
                model_data.model.name if hasattr(model_data, 'model') and model_data.model
                else model_data.get('model', {}).get('name', '')
            )

        return capabilities

    def _infer_capabilities_from_name(self, name: str) -> List[str]:
        """Infer capabilities from model name."""
        name_lower = name.lower()
        capabilities = []

        if 'embedding' in name_lower:
            capabilities.append("embeddings")
        elif 'dall-e' in name_lower:
            capabilities.append("image_generation")
        elif 'whisper' in name_lower:
            capabilities.append("speech_to_text")
        elif 'tts' in name_lower:
            capabilities.append("text_to_speech")
        else:
            # Assume chat capability for GPT models
            capabilities.append("chat")
            if 'gpt-4' in name_lower or 'gpt-5' in name_lower:
                capabilities.append("function_calling")
                capabilities.append("json_mode")
            if 'vision' in name_lower or '4o' in name_lower or '4.1' in name_lower:
                capabilities.append("vision")

        return capabilities

    def _generate_description(self, name: str, capabilities: List[str]) -> str:
        """Generate a default description for a model."""
        name_lower = name.lower()

        if 'embedding' in name_lower:
            return "Text embeddings for search and RAG"
        elif 'dall-e' in name_lower:
            return "Image generation model"
        elif 'whisper' in name_lower:
            return "Speech to text transcription"
        elif 'tts' in name_lower:
            return "Text to speech synthesis"
        elif 'o1' in name_lower or 'o3' in name_lower:
            return "Advanced reasoning model"
        elif 'mini' in name_lower:
            return "Fast and efficient for simple tasks"
        elif 'codex' in name_lower:
            return "Code generation and completion"
        elif 'gpt-4' in name_lower:
            if 'vision' in capabilities:
                return "GPT-4 model with vision capabilities"
            return "Advanced GPT-4 language model"
        elif 'gpt-3' in name_lower:
            return "GPT-3.5 language model"
        else:
            return f"AI model: {name}"

    def _get_context_window(self, name: str) -> int:
        """Get known context window size for a model."""
        # Known context windows for common models
        context_windows = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-turbo": 128000,
            "gpt-4.1": 128000,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
            "o1-preview": 128000,
            "o1-mini": 128000,
            "o3-mini": 200000,
            "text-embedding-3-large": 8191,
            "text-embedding-3-small": 8191,
            "text-embedding-ada-002": 8191,
        }

        name_lower = name.lower()
        for model_name, window in context_windows.items():
            if model_name in name_lower:
                return window

        return 0  # Unknown

    def _get_max_output(self, name: str) -> int:
        """Get known max output tokens for a model."""
        max_outputs = {
            "gpt-4o": 16384,
            "gpt-4o-mini": 16384,
            "gpt-4": 8192,
            "gpt-4-turbo": 4096,
            "gpt-4.1": 16384,
            "gpt-3.5-turbo": 4096,
            "o1-preview": 32768,
            "o1-mini": 65536,
            "o3-mini": 100000,
        }

        name_lower = name.lower()
        for model_name, output in max_outputs.items():
            if model_name in name_lower:
                return output

        return 0  # Unknown

    def get_model_by_name(self, name: str) -> Optional[CatalogModel]:
        """
        Get a specific model by name.

        Args:
            name: The model name to find

        Returns:
            CatalogModel if found, None otherwise
        """
        models = self.get_available_models()
        for model in models:
            if model.name.lower() == name.lower():
                return model
        return None

    def search_models(self, query: str) -> List[CatalogModel]:
        """
        Search models by name or description.

        Args:
            query: Search query string

        Returns:
            List of matching CatalogModel objects
        """
        query_lower = query.lower()
        models = self.get_available_models()

        return [
            model for model in models
            if query_lower in model.name.lower()
            or query_lower in model.description.lower()
            or any(query_lower in cap.lower() for cap in model.capabilities)
        ]

    def get_models_by_capability(self, capability: str) -> List[CatalogModel]:
        """
        Get models that have a specific capability.

        Args:
            capability: The capability to filter by (e.g., "chat", "embeddings")

        Returns:
            List of CatalogModel objects with the capability
        """
        capability_lower = capability.lower()
        models = self.get_available_models()

        return [
            model for model in models
            if capability_lower in [cap.lower() for cap in model.capabilities]
        ]
