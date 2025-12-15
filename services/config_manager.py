"""Configuration manager for Azure Model Manager."""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AzureConfig:
    """Azure-specific configuration."""
    subscription_id: str
    resource_group: str
    ai_services_account: str
    apim_name: str
    location: str


@dataclass
class PortalConfig:
    """APIM Portal configuration."""
    product_id: str
    auto_publish: bool
    endpoint_url: str


class ConfigManager:
    """Manages application configuration loading and saving."""

    DEFAULT_CONFIG_FILENAME = "config.json"
    EXAMPLE_CONFIG_FILENAME = "config.example.json"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config manager.

        Args:
            config_path: Optional custom path to config file.
                        If not provided, uses config.json in the app directory.
        """
        self._config_path = config_path or self._get_default_config_path()
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _get_default_config_path(self) -> str:
        """Get the default configuration file path."""
        # Get the directory where the script is located
        app_dir = Path(__file__).parent.parent
        return str(app_dir / self.DEFAULT_CONFIG_FILENAME)

    def _load_config(self) -> None:
        """Load configuration from file."""
        config_path = Path(self._config_path)

        if not config_path.exists():
            # Try to copy from example config
            example_path = config_path.parent / self.EXAMPLE_CONFIG_FILENAME
            if example_path.exists():
                logger.info(f"Copying example config from {example_path}")
                with open(example_path, 'r') as f:
                    self._config = json.load(f)
                self.save()
            else:
                logger.warning("No configuration file found, using defaults")
                self._config = self._get_default_config()
                self.save()
        else:
            try:
                with open(config_path, 'r') as f:
                    self._config = json.load(f)
                logger.info(f"Configuration loaded from {config_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse config file: {e}")
                raise ValueError(f"Invalid configuration file: {e}")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "azure": {
                "subscription_id": "",
                "resource_group": "",
                "ai_services_account": "",
                "apim_name": "",
                "location": "eastus2"
            },
            "defaults": {
                "capacity_tpm": 10000,
                "content_filter": "Default"
            },
            "portal": {
                "product_id": "internal-ai",
                "auto_publish": False,
                "endpoint_url": ""
            },
            "model_descriptions": {}
        }

    def save(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self._config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
            logger.info(f"Configuration saved to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise

    @property
    def config_path(self) -> str:
        """Get the configuration file path."""
        return self._config_path

    # Azure Configuration Properties
    @property
    def azure(self) -> AzureConfig:
        """Get Azure configuration."""
        azure_cfg = self._config.get("azure", {})
        return AzureConfig(
            subscription_id=azure_cfg.get("subscription_id", ""),
            resource_group=azure_cfg.get("resource_group", ""),
            ai_services_account=azure_cfg.get("ai_services_account", ""),
            apim_name=azure_cfg.get("apim_name", ""),
            location=azure_cfg.get("location", "eastus2")
        )

    @property
    def subscription_id(self) -> str:
        """Get Azure subscription ID."""
        return self._config.get("azure", {}).get("subscription_id", "")

    @property
    def resource_group(self) -> str:
        """Get Azure resource group name."""
        return self._config.get("azure", {}).get("resource_group", "")

    @property
    def ai_services_account(self) -> str:
        """Get AI Services account name."""
        return self._config.get("azure", {}).get("ai_services_account", "")

    @property
    def apim_name(self) -> str:
        """Get APIM instance name."""
        return self._config.get("azure", {}).get("apim_name", "")

    @property
    def location(self) -> str:
        """Get Azure location."""
        return self._config.get("azure", {}).get("location", "eastus2")

    # Default Settings Properties
    @property
    def default_capacity_tpm(self) -> int:
        """Get default capacity in TPM."""
        return self._config.get("defaults", {}).get("capacity_tpm", 10000)

    @property
    def default_content_filter(self) -> str:
        """Get default content filter policy."""
        return self._config.get("defaults", {}).get("content_filter", "Default")

    # Portal Configuration Properties
    @property
    def portal(self) -> PortalConfig:
        """Get portal configuration."""
        portal_cfg = self._config.get("portal", {})
        return PortalConfig(
            product_id=portal_cfg.get("product_id", "internal-ai"),
            auto_publish=portal_cfg.get("auto_publish", False),
            endpoint_url=portal_cfg.get("endpoint_url", "")
        )

    @property
    def product_id(self) -> str:
        """Get APIM product ID."""
        return self._config.get("portal", {}).get("product_id", "internal-ai")

    @property
    def auto_publish(self) -> bool:
        """Get auto-publish setting."""
        return self._config.get("portal", {}).get("auto_publish", False)

    @property
    def endpoint_url(self) -> str:
        """Get the API endpoint URL."""
        return self._config.get("portal", {}).get("endpoint_url", "")

    # Model Descriptions
    @property
    def model_descriptions(self) -> Dict[str, str]:
        """Get model descriptions mapping."""
        return self._config.get("model_descriptions", {})

    def get_model_description(self, model_name: str) -> str:
        """Get description for a specific model."""
        return self.model_descriptions.get(model_name, "")

    def set_model_description(self, model_name: str, description: str) -> None:
        """Set description for a specific model."""
        if "model_descriptions" not in self._config:
            self._config["model_descriptions"] = {}
        self._config["model_descriptions"][model_name] = description

    def update_model_descriptions(self, descriptions: Dict[str, str]) -> None:
        """Update multiple model descriptions."""
        if "model_descriptions" not in self._config:
            self._config["model_descriptions"] = {}
        self._config["model_descriptions"].update(descriptions)
        self.save()

    # Validation
    def is_valid(self) -> bool:
        """Check if configuration has all required values."""
        required = [
            self.subscription_id,
            self.resource_group,
            self.ai_services_account
        ]
        return all(required)

    def get_validation_errors(self) -> list:
        """Get list of validation errors."""
        errors = []
        if not self.subscription_id:
            errors.append("Azure subscription ID is required")
        if not self.resource_group:
            errors.append("Resource group name is required")
        if not self.ai_services_account:
            errors.append("AI Services account name is required")
        return errors

    # Raw access
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self._config[key] = value

    def to_dict(self) -> Dict[str, Any]:
        """Get the full configuration as a dictionary."""
        return self._config.copy()
