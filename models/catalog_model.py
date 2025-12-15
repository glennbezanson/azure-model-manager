"""Data class for Azure AI model catalog models."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CatalogModel:
    """Represents a model from the Azure AI model catalog."""

    name: str                                    # e.g., "gpt-4o"
    version: str                                 # e.g., "2024-11-20"
    publisher: str = "OpenAI"                    # e.g., "OpenAI"
    description: str = ""                        # Full description text
    capabilities: List[str] = field(default_factory=list)  # e.g., ["chat", "vision"]
    context_window: int = 0                      # e.g., 128000
    max_output_tokens: int = 0                   # e.g., 16384
    deprecation_date: Optional[str] = None       # ISO date string if deprecated
    available_skus: List[str] = field(default_factory=list)  # Available deployment SKUs
    regions: List[str] = field(default_factory=list)         # Available regions
    is_deployed: bool = False                    # Set by comparing with deployments
    deployment_name: Optional[str] = None        # If deployed, the deployment name
    model_format: str = "OpenAI"                 # Model format (OpenAI, etc.)
    fine_tune_capable: bool = False              # Whether model supports fine-tuning

    @property
    def display_name(self) -> str:
        """Return a display-friendly name with version."""
        return f"{self.name} ({self.version})"

    @property
    def is_deprecated(self) -> bool:
        """Check if model is deprecated."""
        return self.deprecation_date is not None

    @property
    def capabilities_str(self) -> str:
        """Return capabilities as a comma-separated string."""
        return ", ".join(self.capabilities) if self.capabilities else "N/A"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "version": self.version,
            "publisher": self.publisher,
            "description": self.description,
            "capabilities": self.capabilities,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "deprecation_date": self.deprecation_date,
            "available_skus": self.available_skus,
            "regions": self.regions,
            "is_deployed": self.is_deployed,
            "deployment_name": self.deployment_name,
            "model_format": self.model_format,
            "fine_tune_capable": self.fine_tune_capable
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogModel":
        """Create a CatalogModel from a dictionary."""
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            publisher=data.get("publisher", "OpenAI"),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            context_window=data.get("context_window", 0),
            max_output_tokens=data.get("max_output_tokens", 0),
            deprecation_date=data.get("deprecation_date"),
            available_skus=data.get("available_skus", []),
            regions=data.get("regions", []),
            is_deployed=data.get("is_deployed", False),
            deployment_name=data.get("deployment_name"),
            model_format=data.get("model_format", "OpenAI"),
            fine_tune_capable=data.get("fine_tune_capable", False)
        )

    @classmethod
    def from_azure_response(cls, model_data: dict) -> "CatalogModel":
        """Create a CatalogModel from Azure API response."""
        # Handle the nested structure from Azure API
        model_info = model_data.get("model", {})
        properties = model_data.get("properties", {})

        # Extract capabilities from the model
        capabilities = []
        caps = properties.get("capabilities", {})
        if caps.get("chatCompletion"):
            capabilities.append("chat")
        if caps.get("completion"):
            capabilities.append("completion")
        if caps.get("embeddings"):
            capabilities.append("embeddings")
        if caps.get("imageGeneration"):
            capabilities.append("image_generation")
        if caps.get("vision"):
            capabilities.append("vision")
        if caps.get("functionCalling"):
            capabilities.append("function_calling")
        if caps.get("jsonMode"):
            capabilities.append("json_mode")

        return cls(
            name=model_info.get("name", model_data.get("name", "")),
            version=model_info.get("version", ""),
            publisher=model_info.get("publisher", "OpenAI"),
            description=properties.get("description", ""),
            capabilities=capabilities,
            context_window=properties.get("maxContextLength", 0),
            max_output_tokens=properties.get("maxOutputTokens", 0),
            deprecation_date=properties.get("deprecationDate"),
            available_skus=properties.get("skus", []),
            regions=properties.get("regions", []),
            model_format=model_info.get("format", "OpenAI"),
            fine_tune_capable=properties.get("fineTuneCapable", False)
        )
