"""Service for fetching Azure resource configurations."""
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

import requests
from azure.core.exceptions import HttpResponseError

from services.azure_auth import AzureAuthService
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class RaiPolicy:
    """Represents an Azure RAI (Responsible AI) content filter policy."""
    name: str
    policy_type: str  # SystemManaged or UserManaged
    mode: str  # Blocking, etc.

    @property
    def display_name(self) -> str:
        """Get display-friendly name."""
        # Remove Microsoft. prefix for display
        if self.name.startswith("Microsoft."):
            return self.name[10:]  # Remove "Microsoft."
        return self.name


@dataclass
class ModelQuota:
    """Represents quota/limits for a specific model."""
    model_name: str
    max_tpm: int  # Maximum tokens per minute (in actual tokens, not thousands)
    current_usage: int
    sku_type: str  # Standard, GlobalStandard, etc.

    @property
    def available_tpm(self) -> int:
        """Get available TPM."""
        return max(0, self.max_tpm - self.current_usage)


class AzureResourcesService:
    """Service for fetching Azure resource configurations like RAI policies and quotas."""

    def __init__(self, config: ConfigManager, auth_service: AzureAuthService):
        """
        Initialize the Azure resources service.

        Args:
            config: Configuration manager instance
            auth_service: Azure authentication service instance
        """
        self.config = config
        self.auth_service = auth_service
        self._rai_policies_cache: List[RaiPolicy] = []
        self._quotas_cache: Dict[str, ModelQuota] = {}

    def _get_access_token(self) -> str:
        """Get an access token for Azure Management API."""
        token = self.auth_service.credential.get_token(
            "https://management.azure.com/.default"
        )
        return token.token

    def _make_request(self, url: str) -> dict:
        """Make an authenticated request to Azure REST API."""
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_rai_policies(self, force_refresh: bool = False) -> List[RaiPolicy]:
        """
        Get available RAI (content filter) policies.

        Args:
            force_refresh: If True, bypass cache

        Returns:
            List of RaiPolicy objects
        """
        if not force_refresh and self._rai_policies_cache:
            return self._rai_policies_cache

        try:
            url = (
                f"https://management.azure.com/subscriptions/{self.config.subscription_id}"
                f"/resourceGroups/{self.config.resource_group}"
                f"/providers/Microsoft.CognitiveServices/accounts/{self.config.ai_services_account}"
                f"/raiPolicies?api-version=2024-10-01"
            )

            data = self._make_request(url)
            policies = []

            for item in data.get("value", []):
                props = item.get("properties", {})
                policy = RaiPolicy(
                    name=item.get("name", ""),
                    policy_type=props.get("type", "Unknown"),
                    mode=props.get("mode", "Blocking")
                )
                policies.append(policy)

            self._rai_policies_cache = policies
            logger.info(f"Found {len(policies)} RAI policies")
            return policies

        except Exception as e:
            logger.error(f"Error fetching RAI policies: {e}")
            # Return defaults if API fails
            return [
                RaiPolicy(name="Microsoft.Default", policy_type="SystemManaged", mode="Blocking"),
                RaiPolicy(name="Microsoft.DefaultV2", policy_type="SystemManaged", mode="Blocking")
            ]

    def get_rai_policy_names(self, force_refresh: bool = False) -> List[str]:
        """
        Get list of RAI policy names.

        Args:
            force_refresh: If True, bypass cache

        Returns:
            List of policy names
        """
        policies = self.get_rai_policies(force_refresh)
        return [p.name for p in policies]

    def get_model_quotas(self, force_refresh: bool = False) -> Dict[str, ModelQuota]:
        """
        Get quota/limits for all models.

        Args:
            force_refresh: If True, bypass cache

        Returns:
            Dictionary mapping model names to ModelQuota objects
        """
        if not force_refresh and self._quotas_cache:
            return self._quotas_cache

        try:
            url = (
                f"https://management.azure.com/subscriptions/{self.config.subscription_id}"
                f"/providers/Microsoft.CognitiveServices/locations/{self.config.location}"
                f"/usages?api-version=2024-10-01"
            )

            data = self._make_request(url)
            quotas = {}

            for item in data.get("value", []):
                name_obj = item.get("name", {})
                value_name = name_obj.get("value", "")

                # Parse OpenAI.Standard.<model-name> format
                if value_name.startswith("OpenAI.Standard.") and not value_name.endswith("-finetune"):
                    model_name = value_name.replace("OpenAI.Standard.", "")
                    # The limit is in thousands, convert to actual TPM
                    max_tpm = item.get("limit", 0) * 1000
                    current = item.get("currentValue", 0) * 1000

                    if max_tpm > 0:
                        quotas[model_name.lower()] = ModelQuota(
                            model_name=model_name,
                            max_tpm=max_tpm,
                            current_usage=current,
                            sku_type="Standard"
                        )

                # Also handle GlobalStandard
                elif value_name.startswith("OpenAI.GlobalStandard."):
                    model_name = value_name.replace("OpenAI.GlobalStandard.", "")
                    max_tpm = item.get("limit", 0) * 1000
                    current = item.get("currentValue", 0) * 1000

                    if max_tpm > 0:
                        key = f"{model_name.lower()}_global"
                        quotas[key] = ModelQuota(
                            model_name=model_name,
                            max_tpm=max_tpm,
                            current_usage=current,
                            sku_type="GlobalStandard"
                        )

            self._quotas_cache = quotas
            logger.info(f"Found quotas for {len(quotas)} models")
            return quotas

        except Exception as e:
            logger.error(f"Error fetching model quotas: {e}")
            return {}

    def get_model_max_tpm(self, model_name: str, sku_type: str = "Standard") -> int:
        """
        Get the maximum TPM for a specific model.

        Args:
            model_name: The model name (e.g., "gpt-4o")
            sku_type: SKU type (Standard, GlobalStandard)

        Returns:
            Maximum TPM, or 0 if not found
        """
        quotas = self.get_model_quotas()

        # Try exact match first
        key = model_name.lower()
        if sku_type == "GlobalStandard":
            key = f"{key}_global"

        if key in quotas:
            return quotas[key].max_tpm

        # Try partial match (e.g., "gpt-4o-2024" matches "gpt-4o")
        for quota_key, quota in quotas.items():
            if quota_key.startswith(model_name.lower().replace("-", "")):
                return quota.max_tpm

        return 0  # Unknown

    def get_suggested_capacities(self, model_name: str, sku_type: str = "Standard") -> List[int]:
        """
        Get suggested capacity options for a model based on its quota.

        Args:
            model_name: The model name
            sku_type: SKU type

        Returns:
            List of suggested TPM values
        """
        max_tpm = self.get_model_max_tpm(model_name, sku_type)

        if max_tpm <= 0:
            # Return default options if quota unknown
            return [1000, 5000, 10000, 20000, 50000, 100000]

        # Generate reasonable options up to max
        options = []
        for val in [1000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000]:
            if val <= max_tpm:
                options.append(val)

        # Always include max if not already there
        if max_tpm not in options and max_tpm > 0:
            options.append(max_tpm)
            options.sort()

        return options if options else [1000, 5000, 10000]

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._rai_policies_cache = []
        self._quotas_cache = {}
        logger.info("Azure resources cache cleared")
