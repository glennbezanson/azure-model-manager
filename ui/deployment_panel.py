"""Deployment settings panel for Azure Model Manager."""
import logging
from typing import Optional, TYPE_CHECKING

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QComboBox, QGroupBox, QSpinBox
)
from PyQt6.QtCore import pyqtSignal

from models.deployment import DeploymentSettings

if TYPE_CHECKING:
    from services.azure_resources import AzureResourcesService

logger = logging.getLogger(__name__)


class DeploymentPanel(QWidget):
    """Panel for configuring deployment settings."""

    # Signals
    settings_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, resources_service: Optional["AzureResourcesService"] = None):
        super().__init__(parent)
        self._settings = DeploymentSettings()
        self._resources_service = resources_service
        self._setup_ui()
        self._connect_signals()
        self._load_azure_data()
        self._load_defaults()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        group = QGroupBox("Deployment Settings")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)

        layout = QHBoxLayout(group)

        # Deployment Name
        name_layout = QVBoxLayout()
        name_label = QLabel("Deployment Name:")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Auto-generated from model name")
        self.name_edit.setToolTip(
            "Custom deployment name. Leave empty to auto-generate from model name."
        )
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout, 2)

        # Capacity (TPM)
        capacity_layout = QVBoxLayout()
        capacity_label = QLabel("Capacity (TPM):")
        self.capacity_combo = QComboBox()
        self.capacity_combo.setEditable(True)
        self.capacity_combo.setToolTip(
            "Tokens per minute capacity. Higher values allow more throughput."
        )
        # Add preset values
        for capacity in DeploymentSettings.CAPACITY_OPTIONS:
            self.capacity_combo.addItem(f"{capacity:,}", capacity)
        capacity_layout.addWidget(capacity_label)
        capacity_layout.addWidget(self.capacity_combo)
        layout.addLayout(capacity_layout, 1)

        # Content Filter
        filter_layout = QVBoxLayout()
        filter_label = QLabel("Content Filter:")
        self.filter_combo = QComboBox()
        self.filter_combo.setToolTip(
            "Content filter policy to apply to the deployment."
        )
        # Will be populated dynamically from Azure, fallback to defaults
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_combo)
        layout.addLayout(filter_layout, 1)

        # SKU
        sku_layout = QVBoxLayout()
        sku_label = QLabel("SKU:")
        self.sku_combo = QComboBox()
        self.sku_combo.addItems(["Standard", "ProvisionedManaged", "GlobalStandard"])
        self.sku_combo.setToolTip("Deployment SKU type.")
        sku_layout.addWidget(sku_label)
        sku_layout.addWidget(self.sku_combo)
        layout.addLayout(sku_layout, 1)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.name_edit.textChanged.connect(self._on_settings_changed)
        self.capacity_combo.currentTextChanged.connect(self._on_settings_changed)
        self.filter_combo.currentTextChanged.connect(self._on_settings_changed)
        self.sku_combo.currentTextChanged.connect(self._on_settings_changed)

    def _load_azure_data(self) -> None:
        """Load RAI policies and quotas from Azure."""
        # Load RAI policies for content filter dropdown
        if self._resources_service:
            try:
                policies = self._resources_service.get_rai_policy_names()
                if policies:
                    self.filter_combo.clear()
                    for policy in policies:
                        self.filter_combo.addItem(policy)
                    logger.info(f"Loaded {len(policies)} RAI policies from Azure")
                else:
                    # Fallback to defaults
                    self._load_default_filters()
            except Exception as e:
                logger.warning(f"Failed to load RAI policies from Azure: {e}")
                self._load_default_filters()
        else:
            self._load_default_filters()

    def _load_default_filters(self) -> None:
        """Load default content filter options."""
        self.filter_combo.clear()
        for filter_name in DeploymentSettings.CONTENT_FILTER_OPTIONS:
            self.filter_combo.addItem(filter_name)

    def _load_defaults(self) -> None:
        """Load default settings."""
        # Set default capacity
        default_capacity = self._settings.capacity_tpm
        index = self.capacity_combo.findData(default_capacity)
        if index >= 0:
            self.capacity_combo.setCurrentIndex(index)
        else:
            self.capacity_combo.setCurrentText(f"{default_capacity:,}")

        # Set default content filter
        index = self.filter_combo.findText(self._settings.content_filter)
        if index >= 0:
            self.filter_combo.setCurrentIndex(index)

        # Set default SKU
        index = self.sku_combo.findText(self._settings.sku_name)
        if index >= 0:
            self.sku_combo.setCurrentIndex(index)

    def _on_settings_changed(self) -> None:
        """Handle settings changes."""
        self.settings_changed.emit()

    def get_settings(self) -> DeploymentSettings:
        """
        Get the current deployment settings.

        Returns:
            DeploymentSettings object with current values
        """
        # Parse capacity (remove commas if present)
        capacity_text = self.capacity_combo.currentText().replace(",", "")
        try:
            capacity = int(capacity_text)
        except ValueError:
            capacity = self._settings.capacity_tpm

        return DeploymentSettings(
            deployment_name=self.name_edit.text().strip(),
            capacity_tpm=capacity,
            content_filter=self.filter_combo.currentText(),
            sku_name=self.sku_combo.currentText()
        )

    def set_settings(self, settings: DeploymentSettings) -> None:
        """
        Set deployment settings.

        Args:
            settings: DeploymentSettings to apply
        """
        self._settings = settings

        # Block signals during update
        self.name_edit.blockSignals(True)
        self.capacity_combo.blockSignals(True)
        self.filter_combo.blockSignals(True)
        self.sku_combo.blockSignals(True)

        self.name_edit.setText(settings.deployment_name)

        # Set capacity
        index = self.capacity_combo.findData(settings.capacity_tpm)
        if index >= 0:
            self.capacity_combo.setCurrentIndex(index)
        else:
            self.capacity_combo.setCurrentText(f"{settings.capacity_tpm:,}")

        # Set filter
        index = self.filter_combo.findText(settings.content_filter)
        if index >= 0:
            self.filter_combo.setCurrentIndex(index)

        # Set SKU
        index = self.sku_combo.findText(settings.sku_name)
        if index >= 0:
            self.sku_combo.setCurrentIndex(index)

        self.name_edit.blockSignals(False)
        self.capacity_combo.blockSignals(False)
        self.filter_combo.blockSignals(False)
        self.sku_combo.blockSignals(False)

    def set_deployment_name(self, name: str) -> None:
        """
        Set the deployment name.

        Args:
            name: Deployment name to set
        """
        self.name_edit.setText(name)

    def get_deployment_name(self) -> str:
        """
        Get the deployment name.

        Returns:
            Current deployment name
        """
        return self.name_edit.text().strip()

    def clear_deployment_name(self) -> None:
        """Clear the deployment name field."""
        self.name_edit.clear()

    def set_capacity(self, capacity_tpm: int) -> None:
        """
        Set the capacity.

        Args:
            capacity_tpm: Capacity in tokens per minute
        """
        index = self.capacity_combo.findData(capacity_tpm)
        if index >= 0:
            self.capacity_combo.setCurrentIndex(index)
        else:
            self.capacity_combo.setCurrentText(f"{capacity_tpm:,}")

    def get_capacity(self) -> int:
        """
        Get the capacity.

        Returns:
            Capacity in tokens per minute
        """
        capacity_text = self.capacity_combo.currentText().replace(",", "")
        try:
            return int(capacity_text)
        except ValueError:
            return 10000

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the panel.

        Args:
            enabled: Whether to enable the panel
        """
        self.name_edit.setEnabled(enabled)
        self.capacity_combo.setEnabled(enabled)
        self.filter_combo.setEnabled(enabled)
        self.sku_combo.setEnabled(enabled)

    def load_from_config(self, default_capacity: int, default_filter: str) -> None:
        """
        Load defaults from configuration.

        Args:
            default_capacity: Default capacity from config
            default_filter: Default content filter from config
        """
        self._settings.capacity_tpm = default_capacity
        self._settings.content_filter = default_filter
        self._load_defaults()

    def set_available_skus(self, skus: list) -> None:
        """
        Set the available SKUs for the current model and auto-select the first one.

        Args:
            skus: List of available SKU names for the model
        """
        self.sku_combo.blockSignals(True)

        # Clear and repopulate
        self.sku_combo.clear()

        if skus:
            for sku in skus:
                self.sku_combo.addItem(sku)
            # Auto-select the first (usually only) supported SKU
            self.sku_combo.setCurrentIndex(0)
            logger.info(f"Set available SKUs: {skus}, selected: {skus[0]}")
        else:
            # Fallback to defaults if no SKUs specified
            self.sku_combo.addItems(["Standard", "ProvisionedManaged", "GlobalStandard"])
            self.sku_combo.setCurrentText("Standard")

        self.sku_combo.blockSignals(False)

    def reset_skus_to_default(self) -> None:
        """Reset SKU options to default list."""
        self.sku_combo.blockSignals(True)
        self.sku_combo.clear()
        self.sku_combo.addItems(["Standard", "ProvisionedManaged", "GlobalStandard"])
        self.sku_combo.setCurrentText("Standard")
        self.sku_combo.blockSignals(False)
