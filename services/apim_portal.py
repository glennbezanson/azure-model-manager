"""Service for updating Azure API Management Developer Portal content."""
import logging
import re
from typing import List, Optional, Dict, Any
from datetime import datetime

import requests
from azure.mgmt.apimanagement import ApiManagementClient
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from services.azure_auth import AzureAuthService
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class APIMPortalService:
    """Service for updating the APIM Developer Portal with model information."""

    def __init__(self, config: ConfigManager, auth_service: AzureAuthService):
        """
        Initialize the APIM Portal service.

        Args:
            config: Configuration manager instance
            auth_service: Azure authentication service instance
        """
        self.config = config
        self.auth_service = auth_service
        self._client: Optional[ApiManagementClient] = None

    @property
    def client(self) -> ApiManagementClient:
        """Get or create the API Management client."""
        if self._client is None:
            self._client = ApiManagementClient(
                credential=self.auth_service.credential,
                subscription_id=self.config.subscription_id
            )
        return self._client

    def get_product(self, product_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get product details.

        Args:
            product_id: Product ID (default: from config)

        Returns:
            Product details as dictionary
        """
        product_id = product_id or self.config.product_id

        try:
            product = self.client.product.get(
                resource_group_name=self.config.resource_group,
                service_name=self.config.apim_name,
                product_id=product_id
            )
            return {
                "id": product.id,
                "name": product.name,
                "display_name": product.display_name,
                "description": product.description or "",
                "state": product.state,
                "subscription_required": product.subscription_required,
                "approval_required": product.approval_required,
                "terms": product.terms
            }
        except ResourceNotFoundError:
            logger.error(f"Product '{product_id}' not found")
            raise
        except Exception as e:
            logger.error(f"Error getting product: {e}")
            raise

    def get_current_description(self, product_id: Optional[str] = None) -> str:
        """
        Get the current product description.

        Args:
            product_id: Product ID (default: from config)

        Returns:
            Current description text
        """
        product = self.get_product(product_id)
        return product.get("description", "")

    def generate_models_text(self, deployed_models: List[Dict[str, str]]) -> str:
        """
        Generate the Available Models text section.

        Args:
            deployed_models: List of dicts with deployment_name and description

        Returns:
            Formatted text for the models section (one model per line)
        """
        if not deployed_models:
            return "No models currently deployed"

        # Simple format: one model name per line
        lines = []
        for model in deployed_models:
            name = model.get("deployment_name", "")
            if name:
                lines.append(name)

        return "\n".join(lines)

    def update_models_list(
        self,
        deployed_models: List[Dict[str, str]],
        product_id: Optional[str] = None,
        custom_text: Optional[str] = None
    ) -> bool:
        """
        Update the product description with the model list.

        Args:
            deployed_models: List of dicts with deployment_name and description
            product_id: Product ID (default: from config)
            custom_text: Optional custom text to use instead of generating

        Returns:
            True if update successful
        """
        product_id = product_id or self.config.product_id

        try:
            # Get current product
            product = self.get_product(product_id)

            # Generate new models list (one model per line)
            if custom_text:
                updated_description = custom_text
            else:
                updated_description = self.generate_models_text(deployed_models)

            # Update the product description with just the model list
            self.client.product.update(
                resource_group_name=self.config.resource_group,
                service_name=self.config.apim_name,
                product_id=product_id,
                if_match="*",
                parameters={
                    "properties": {
                        "displayName": product.get("display_name"),
                        "description": updated_description,
                        "subscriptionRequired": product.get("subscription_required", True),
                        "approvalRequired": product.get("approval_required", False),
                        "state": product.get("state", "published")
                    }
                }
            )

            logger.info(f"Successfully updated product '{product_id}' with {len(deployed_models)} models")
            return True

        except HttpResponseError as e:
            logger.error(f"Azure API error updating product: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error updating models list: {e}")
            raise

    def _update_endpoint_url(self, description: str, new_url: str) -> str:
        """
        Update endpoint URLs in the description.

        Args:
            description: Current description text
            new_url: New endpoint URL

        Returns:
            Updated description with new URL
        """
        # Pattern to match common endpoint URL formats
        patterns = [
            r"https://[a-zA-Z0-9-]+\.azure-api\.net/[a-zA-Z0-9/-]+",
            r"Endpoint:\s*`[^`]+`",
            r"Base URL:\s*`[^`]+`"
        ]

        updated = description
        for pattern in patterns:
            if "Endpoint:" in pattern or "Base URL:" in pattern:
                replacement = pattern.split(":")[0] + f": `{new_url}`"
            else:
                replacement = new_url
            updated = re.sub(pattern, replacement, updated, count=1)

        return updated

    def republish_portal(self) -> bool:
        """
        Trigger portal republish to make changes live.

        Returns:
            True if republish initiated successfully
        """
        try:
            token = self.auth_service.get_access_token()
            if not token:
                raise RuntimeError("Failed to get access token")

            revision_name = f"publish-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            url = (
                f"https://management.azure.com/subscriptions/{self.config.subscription_id}"
                f"/resourceGroups/{self.config.resource_group}"
                f"/providers/Microsoft.ApiManagement/service/{self.config.apim_name}"
                f"/portalRevisions/{revision_name}?api-version=2022-08-01"
            )

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            body = {
                "properties": {
                    "description": f"Model list update {datetime.now().isoformat()}",
                    "isCurrent": True
                }
            }

            response = requests.put(url, headers=headers, json=body, timeout=60)

            if response.status_code in [200, 201, 202]:
                logger.info("Portal republish initiated successfully")
                return True
            else:
                logger.error(f"Portal republish failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error republishing portal: {e}")
            raise

    def update_and_publish(
        self,
        deployed_models: List[Dict[str, str]],
        product_id: Optional[str] = None,
        custom_text: Optional[str] = None
    ) -> bool:
        """
        Update the models list and optionally republish the portal.

        Args:
            deployed_models: List of dicts with deployment_name and description
            product_id: Product ID (default: from config)
            custom_text: Optional custom text to use instead of generating

        Returns:
            True if both operations successful
        """
        # Update the product description
        self.update_models_list(deployed_models, product_id, custom_text)

        # Republish if auto_publish is enabled
        if self.config.auto_publish:
            return self.republish_portal()

        return True

    def get_portal_content_items(self) -> List[Dict[str, Any]]:
        """
        Get all portal content items (for advanced editing).

        Returns:
            List of content items
        """
        try:
            token = self.auth_service.get_access_token()
            if not token:
                raise RuntimeError("Failed to get access token")

            url = (
                f"https://management.azure.com/subscriptions/{self.config.subscription_id}"
                f"/resourceGroups/{self.config.resource_group}"
                f"/providers/Microsoft.ApiManagement/service/{self.config.apim_name}"
                f"/contentTypes/document/contentItems?api-version=2022-08-01"
            )

            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                return response.json().get("value", [])
            else:
                logger.warning(f"Failed to get content items: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error getting portal content: {e}")
            return []

    def preview_update(
        self,
        deployed_models: List[Dict[str, str]],
        product_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Preview what the update would look like without applying it.

        Args:
            deployed_models: List of dicts with deployment_name and description
            product_id: Product ID (default: from config)

        Returns:
            Dict with 'current' and 'updated' description text
        """
        product_id = product_id or self.config.product_id
        current_description = self.get_current_description(product_id)

        # Generate simple model list (one per line)
        new_models_section = self.generate_models_text(deployed_models)

        return {
            "current": current_description,
            "updated": new_models_section,
            "models_section": new_models_section
        }
