"""Service for managing Azure AI model deployments."""
import logging
from typing import List, Optional, Callable
from datetime import datetime

from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import Deployment as AzureDeployment, DeploymentModel, Sku
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from services.azure_auth import AzureAuthService
from services.config_manager import ConfigManager
from models.deployment import Deployment, DeploymentSettings
from models.catalog_model import CatalogModel

logger = logging.getLogger(__name__)


class DeploymentService:
    """Service for managing model deployments to Azure AI Services."""

    def __init__(self, config: ConfigManager, auth_service: AzureAuthService):
        """
        Initialize the deployment service.

        Args:
            config: Configuration manager instance
            auth_service: Azure authentication service instance
        """
        self.config = config
        self.auth_service = auth_service
        self._client: Optional[CognitiveServicesManagementClient] = None
        self._deployments_cache: List[Deployment] = []

    @property
    def client(self) -> CognitiveServicesManagementClient:
        """Get or create the Cognitive Services management client."""
        if self._client is None:
            self._client = CognitiveServicesManagementClient(
                credential=self.auth_service.credential,
                subscription_id=self.config.subscription_id
            )
        return self._client

    def list_deployments(self, force_refresh: bool = False) -> List[Deployment]:
        """
        List all current deployments.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of Deployment objects
        """
        if not force_refresh and self._deployments_cache:
            return self._deployments_cache

        try:
            deployments = []
            deployment_list = self.client.deployments.list(
                resource_group_name=self.config.resource_group,
                account_name=self.config.ai_services_account
            )

            for deployment_data in deployment_list:
                try:
                    deployment = Deployment.from_azure_response(deployment_data)
                    deployments.append(deployment)
                except Exception as e:
                    logger.warning(f"Failed to parse deployment: {e}")
                    continue

            self._deployments_cache = deployments
            logger.info(f"Found {len(deployments)} deployments")
            return deployments

        except HttpResponseError as e:
            logger.error(f"Azure API error listing deployments: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error listing deployments: {e}")
            raise

    def get_deployment(self, deployment_name: str) -> Optional[Deployment]:
        """
        Get a specific deployment by name.

        Args:
            deployment_name: The deployment name

        Returns:
            Deployment object if found, None otherwise
        """
        try:
            deployment_data = self.client.deployments.get(
                resource_group_name=self.config.resource_group,
                account_name=self.config.ai_services_account,
                deployment_name=deployment_name
            )
            return Deployment.from_azure_response(deployment_data)
        except ResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting deployment {deployment_name}: {e}")
            raise

    def deploy_model(
        self,
        model: CatalogModel,
        deployment_name: str,
        settings: DeploymentSettings,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Deployment:
        """
        Deploy a model to the AI Services account.

        Args:
            model: The CatalogModel to deploy
            deployment_name: Name for the deployment
            settings: Deployment settings (capacity, content filter, etc.)
            progress_callback: Optional callback for progress updates

        Returns:
            The created Deployment object
        """
        if progress_callback:
            progress_callback(f"Starting deployment of {model.name}...")

        try:
            # Create deployment parameters
            deployment = AzureDeployment(
                sku=Sku(
                    name=settings.sku_name,
                    capacity=settings.capacity_tpm // 1000  # Azure uses thousands
                ),
                properties={
                    "model": DeploymentModel(
                        format=model.model_format,
                        name=model.name,
                        version=model.version
                    ),
                    "raiPolicyName": settings.content_filter
                }
            )

            if progress_callback:
                progress_callback(f"Creating deployment '{deployment_name}'...")

            # This is a long-running operation
            poller = self.client.deployments.begin_create_or_update(
                resource_group_name=self.config.resource_group,
                account_name=self.config.ai_services_account,
                deployment_name=deployment_name,
                deployment=deployment
            )

            if progress_callback:
                progress_callback("Waiting for deployment to complete...")

            # Wait for completion
            result = poller.result()

            # Clear cache to force refresh
            self._deployments_cache = []

            if progress_callback:
                progress_callback(f"Deployment '{deployment_name}' completed successfully")

            logger.info(f"Successfully deployed {model.name} as {deployment_name}")
            return Deployment.from_azure_response(result)

        except HttpResponseError as e:
            error_msg = f"Azure API error deploying {model.name}: {e.message}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(f"Error: {e.message}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"Error deploying {model.name}: {str(e)}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            raise

    def delete_deployment(
        self,
        deployment_name: str,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Delete a deployment.

        Args:
            deployment_name: The deployment name to delete
            progress_callback: Optional callback for progress updates

        Returns:
            True if deletion successful
        """
        if progress_callback:
            progress_callback(f"Deleting deployment '{deployment_name}'...")

        try:
            poller = self.client.deployments.begin_delete(
                resource_group_name=self.config.resource_group,
                account_name=self.config.ai_services_account,
                deployment_name=deployment_name
            )

            poller.result()

            # Clear cache
            self._deployments_cache = []

            if progress_callback:
                progress_callback(f"Deployment '{deployment_name}' deleted successfully")

            logger.info(f"Successfully deleted deployment {deployment_name}")
            return True

        except ResourceNotFoundError:
            logger.warning(f"Deployment {deployment_name} not found")
            return True  # Already deleted
        except HttpResponseError as e:
            logger.error(f"Azure API error deleting {deployment_name}: {e.message}")
            if progress_callback:
                progress_callback(f"Error: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error deleting {deployment_name}: {e}")
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            raise

    def update_deployment_capacity(
        self,
        deployment_name: str,
        new_capacity_tpm: int,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Deployment:
        """
        Update the capacity of an existing deployment.

        Args:
            deployment_name: The deployment to update
            new_capacity_tpm: New capacity in TPM
            progress_callback: Optional callback for progress updates

        Returns:
            Updated Deployment object
        """
        if progress_callback:
            progress_callback(f"Updating capacity for '{deployment_name}'...")

        try:
            # Get current deployment
            current = self.get_deployment(deployment_name)
            if not current:
                raise ValueError(f"Deployment '{deployment_name}' not found")

            # Create update parameters
            deployment = AzureDeployment(
                sku=Sku(
                    name=current.sku_name,
                    capacity=new_capacity_tpm // 1000
                )
            )

            poller = self.client.deployments.begin_create_or_update(
                resource_group_name=self.config.resource_group,
                account_name=self.config.ai_services_account,
                deployment_name=deployment_name,
                deployment=deployment
            )

            result = poller.result()
            self._deployments_cache = []

            if progress_callback:
                progress_callback(f"Capacity updated to {new_capacity_tpm:,} TPM")

            return Deployment.from_azure_response(result)

        except Exception as e:
            logger.error(f"Error updating capacity: {e}")
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            raise

    def is_model_deployed(self, model_name: str) -> bool:
        """
        Check if a model is currently deployed.

        Args:
            model_name: The model name to check

        Returns:
            True if the model has at least one deployment
        """
        deployments = self.list_deployments()
        return any(d.model_name.lower() == model_name.lower() for d in deployments)

    def get_deployments_for_model(self, model_name: str) -> List[Deployment]:
        """
        Get all deployments of a specific model.

        Args:
            model_name: The model name

        Returns:
            List of Deployment objects for this model
        """
        deployments = self.list_deployments()
        return [d for d in deployments if d.model_name.lower() == model_name.lower()]

    def get_deployed_models_dict(self) -> List[dict]:
        """
        Get deployed models as a list of dictionaries for portal updates.

        Returns:
            List of dicts with deployment_name, model_name, etc.
        """
        deployments = self.list_deployments()
        return [
            {
                "deployment_name": d.deployment_name,
                "model_name": d.model_name,
                "model_version": d.model_version,
                "description": self.config.get_model_description(d.deployment_name)
                              or self.config.get_model_description(d.model_name)
                              or d.model_name
            }
            for d in deployments
            if d.is_ready
        ]

    def clear_cache(self) -> None:
        """Clear the deployments cache."""
        self._deployments_cache = []
        logger.info("Deployments cache cleared")
