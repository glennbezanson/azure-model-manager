"""Data classes for Azure AI model deployments."""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Deployment:
    """Represents an existing model deployment."""

    deployment_name: str                         # Name of the deployment
    model_name: str                              # Name of the model (e.g., "gpt-4o")
    model_version: str                           # Version of the model
    model_format: str = "OpenAI"                 # Model format
    sku_name: str = "Standard"                   # SKU name
    sku_capacity: int = 0                        # Capacity in TPM (thousands)
    provisioning_state: str = ""                 # Deployment state
    rai_policy_name: Optional[str] = None        # Content filter policy name
    created_at: Optional[datetime] = None        # Creation timestamp
    updated_at: Optional[datetime] = None        # Last update timestamp

    @property
    def is_ready(self) -> bool:
        """Check if deployment is ready for use."""
        return self.provisioning_state.lower() == "succeeded"

    @property
    def display_name(self) -> str:
        """Return a display-friendly name."""
        return f"{self.deployment_name} ({self.model_name})"

    @property
    def capacity_display(self) -> str:
        """Return capacity as formatted string."""
        return f"{self.sku_capacity:,} TPM"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "deployment_name": self.deployment_name,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_format": self.model_format,
            "sku_name": self.sku_name,
            "sku_capacity": self.sku_capacity,
            "provisioning_state": self.provisioning_state,
            "rai_policy_name": self.rai_policy_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Deployment":
        """Create a Deployment from a dictionary."""
        created_at = None
        updated_at = None

        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            updated_at = datetime.fromisoformat(data["updated_at"])

        return cls(
            deployment_name=data.get("deployment_name", ""),
            model_name=data.get("model_name", ""),
            model_version=data.get("model_version", ""),
            model_format=data.get("model_format", "OpenAI"),
            sku_name=data.get("sku_name", "Standard"),
            sku_capacity=data.get("sku_capacity", 0),
            provisioning_state=data.get("provisioning_state", ""),
            rai_policy_name=data.get("rai_policy_name"),
            created_at=created_at,
            updated_at=updated_at
        )

    @classmethod
    def from_azure_response(cls, deployment_data) -> "Deployment":
        """Create a Deployment from Azure SDK response object."""
        # Handle both dict and object responses
        if hasattr(deployment_data, 'name'):
            # SDK object
            props = deployment_data.properties
            model = props.model if props else None
            sku = deployment_data.sku

            return cls(
                deployment_name=deployment_data.name,
                model_name=model.name if model else "",
                model_version=model.version if model else "",
                model_format=model.format if model else "OpenAI",
                sku_name=sku.name if sku else "Standard",
                sku_capacity=sku.capacity if sku else 0,
                provisioning_state=props.provisioning_state if props else "",
                rai_policy_name=props.rai_policy_name if props else None
            )
        else:
            # Dict response
            props = deployment_data.get("properties", {})
            model = props.get("model", {})
            sku = deployment_data.get("sku", {})

            return cls(
                deployment_name=deployment_data.get("name", ""),
                model_name=model.get("name", ""),
                model_version=model.get("version", ""),
                model_format=model.get("format", "OpenAI"),
                sku_name=sku.get("name", "Standard"),
                sku_capacity=sku.get("capacity", 0),
                provisioning_state=props.get("provisioningState", ""),
                rai_policy_name=props.get("raiPolicyName")
            )


@dataclass
class DeploymentSettings:
    """Settings for creating a new deployment."""

    deployment_name: str = ""                    # Custom deployment name
    capacity_tpm: int = 10000                    # Capacity in TPM
    content_filter: str = "Default"              # Content filter policy
    sku_name: str = "Standard"                   # SKU name

    # Available content filter options
    CONTENT_FILTER_OPTIONS = [
        "Default",
        "DefaultV2",
        "CustomFilter"
    ]

    # Common capacity options
    CAPACITY_OPTIONS = [
        1000,
        5000,
        10000,
        20000,
        50000,
        100000
    ]

    def get_deployment_name_for_model(self, model_name: str, model_version: str = "") -> str:
        """Generate deployment name for a model if not custom set."""
        if self.deployment_name:
            return self.deployment_name

        # Generate a default name based on model
        safe_name = model_name.replace(".", "-").lower()
        if model_version:
            safe_version = model_version.replace(".", "-").replace("-", "")[:8]
            return f"{safe_name}-{safe_version}"
        return safe_name

    def to_azure_params(self, model_name: str, model_version: str, model_format: str = "OpenAI") -> dict:
        """Convert to Azure deployment parameters."""
        return {
            "sku": {
                "name": self.sku_name,
                "capacity": self.capacity_tpm // 1000  # Azure uses thousands
            },
            "properties": {
                "model": {
                    "format": model_format,
                    "name": model_name,
                    "version": model_version
                },
                "raiPolicyName": self.content_filter
            }
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "deployment_name": self.deployment_name,
            "capacity_tpm": self.capacity_tpm,
            "content_filter": self.content_filter,
            "sku_name": self.sku_name
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentSettings":
        """Create DeploymentSettings from a dictionary."""
        return cls(
            deployment_name=data.get("deployment_name", ""),
            capacity_tpm=data.get("capacity_tpm", 10000),
            content_filter=data.get("content_filter", "Default"),
            sku_name=data.get("sku_name", "Standard")
        )
