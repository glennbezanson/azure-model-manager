"""Main application window for Azure Model Manager."""
import logging
from typing import Optional, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from ui.model_browser import ModelBrowser
from ui.model_details import ModelDetailsPanel
from ui.deployment_panel import DeploymentPanel
from ui.portal_preview import PortalPreviewPanel
from ui.status_bar import StatusBar

from services.azure_auth import AzureAuthService
from services.config_manager import ConfigManager
from services.model_catalog import ModelCatalogService
from services.deployments import DeploymentService
from services.apim_portal import APIMPortalService
from services.azure_resources import AzureResourcesService
from models.catalog_model import CatalogModel
from models.deployment import DeploymentSettings

logger = logging.getLogger(__name__)


class DeploymentWorker(QThread):
    """Worker thread for model deployments."""

    progress = pyqtSignal(int, str)  # percent, message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(
        self,
        deployment_service: DeploymentService,
        models: List[CatalogModel],
        settings: DeploymentSettings
    ):
        super().__init__()
        self.deployment_service = deployment_service
        self.models = models
        self.settings = settings

    def run(self):
        """Execute the deployments."""
        try:
            total = len(self.models)
            for i, model in enumerate(self.models):
                percent = int((i / total) * 100)
                self.progress.emit(percent, f"Deploying {model.name}...")

                # Generate deployment name
                deployment_name = self.settings.get_deployment_name_for_model(
                    model.name, model.version
                )

                # Deploy
                self.deployment_service.deploy_model(
                    model=model,
                    deployment_name=deployment_name,
                    settings=self.settings,
                    progress_callback=lambda msg: self.progress.emit(percent, msg)
                )

            self.progress.emit(100, "All deployments complete")
            self.finished.emit(True, f"Successfully deployed {total} model(s)")

        except Exception as e:
            logger.error(f"Deployment error: {e}")
            self.finished.emit(False, str(e))


class PortalPublishWorker(QThread):
    """Worker thread for publishing to Developer Portal."""

    progress = pyqtSignal(str)  # status message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(
        self,
        portal_service: 'APIMPortalService',
        deployed_models: list,
        custom_text: str
    ):
        super().__init__()
        self.portal_service = portal_service
        self.deployed_models = deployed_models
        self.custom_text = custom_text

    def run(self):
        """Execute the portal update and publish."""
        try:
            # Step 1: Update product description
            self.progress.emit("Updating product description...")
            self.portal_service.update_models_list(
                deployed_models=self.deployed_models,
                custom_text=self.custom_text
            )

            # Step 2: Publish the portal
            self.progress.emit("Publishing Developer Portal...")
            success = self.portal_service.republish_portal()

            if success:
                self.finished.emit(True, "Portal published successfully")
            else:
                self.finished.emit(False, "Portal publish failed")

        except Exception as e:
            logger.error(f"Portal publish error: {e}")
            self.finished.emit(False, str(e))


class RefreshWorker(QThread):
    """Worker thread for refreshing model data."""

    finished = pyqtSignal(bool, str, list)  # success, message, models

    def __init__(
        self,
        catalog_service: ModelCatalogService,
        deployment_service: DeploymentService
    ):
        super().__init__()
        self.catalog_service = catalog_service
        self.deployment_service = deployment_service

    def run(self):
        """Fetch models and deployments."""
        try:
            # Get available models
            catalog_models = self.catalog_service.get_available_models(force_refresh=True)

            # Get current deployments
            deployments = self.deployment_service.list_deployments(force_refresh=True)

            # Mark deployed models (mark ALL versions of a model as deployed)
            deployment_map = {d.model_name.lower(): d for d in deployments}

            for model in catalog_models:
                if model.name.lower() in deployment_map:
                    deployment = deployment_map[model.name.lower()]
                    model.is_deployed = True
                    model.deployment_name = deployment.deployment_name

            # Filter to show only one entry per model name (prefer deployed, then latest version)
            seen_models = {}
            filtered_models = []
            for model in catalog_models:
                key = model.name.lower()
                if key not in seen_models:
                    seen_models[key] = model
                    filtered_models.append(model)
                elif model.is_deployed and not seen_models[key].is_deployed:
                    # Replace with deployed version
                    filtered_models.remove(seen_models[key])
                    seen_models[key] = model
                    filtered_models.append(model)

            catalog_models = filtered_models

            self.finished.emit(True, f"Loaded {len(catalog_models)} models", catalog_models)

        except Exception as e:
            logger.error(f"Refresh error: {e}")
            self.finished.emit(False, str(e), [])


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Azure AI Model Manager")
        self.setMinimumSize(1200, 800)

        # Initialize services
        self._init_services()

        # Set up UI
        self._setup_ui()
        self._connect_signals()

        # Workers
        self._deployment_worker: Optional[DeploymentWorker] = None
        self._refresh_worker: Optional[RefreshWorker] = None
        self._portal_worker: Optional[PortalPublishWorker] = None

        # Blink timer for publishing state
        self._blink_timer = QTimer()
        self._blink_timer.timeout.connect(self._toggle_button_blink)
        self._blink_state = False
        self._original_button_text = ""

        # Initial load
        self._check_auth_and_load()

    def _init_services(self) -> None:
        """Initialize Azure services."""
        self.config = ConfigManager()
        self.auth_service = AzureAuthService()
        self.catalog_service = ModelCatalogService(self.config, self.auth_service)
        self.deployment_service = DeploymentService(self.config, self.auth_service)
        self.portal_service = APIMPortalService(self.config, self.auth_service)
        self.resources_service = AzureResourcesService(self.config, self.auth_service)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Top section: Model browser and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Model browser (left)
        self.model_browser = ModelBrowser()
        self.model_browser.setMinimumWidth(280)
        splitter.addWidget(self.model_browser)

        # Model details (right)
        self.model_details = ModelDetailsPanel()
        splitter.addWidget(self.model_details)

        splitter.setSizes([300, 700])
        main_layout.addWidget(splitter, 3)

        # Deployment settings
        self.deployment_panel = DeploymentPanel(resources_service=self.resources_service)
        self.deployment_panel.load_from_config(
            self.config.default_capacity_tpm,
            self.config.default_content_filter
        )
        main_layout.addWidget(self.deployment_panel)

        # Portal preview
        self.portal_preview = PortalPreviewPanel()
        main_layout.addWidget(self.portal_preview, 2)

        # Action buttons
        button_layout = QHBoxLayout()

        self.deploy_btn = QPushButton("Deploy Selected")
        self.deploy_btn.setToolTip("Deploy all checked models")
        self.deploy_btn.setEnabled(False)

        self.delete_btn = QPushButton("Delete Deployment")
        self.delete_btn.setToolTip("Delete the selected deployment")
        self.delete_btn.setEnabled(False)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh model list from Azure")

        self.update_portal_btn = QPushButton("Update Portal")
        self.update_portal_btn.setToolTip("Update Developer Portal with current models")

        self.deploy_and_update_btn = QPushButton("Deploy && Update Portal")
        self.deploy_and_update_btn.setToolTip("Deploy selected models and update portal")
        self.deploy_and_update_btn.setEnabled(False)

        button_layout.addWidget(self.deploy_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.update_portal_btn)
        button_layout.addWidget(self.deploy_and_update_btn)

        main_layout.addLayout(button_layout)

        # Status bar
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        # Model browser signals
        self.model_browser.model_selected.connect(self._on_model_selected)
        self.model_browser.selection_changed.connect(self._on_selection_changed)

        # Button signals
        self.deploy_btn.clicked.connect(self._deploy_selected)
        self.delete_btn.clicked.connect(self._delete_deployment)
        self.refresh_btn.clicked.connect(self._refresh_models)
        self.update_portal_btn.clicked.connect(self._update_portal)
        self.deploy_and_update_btn.clicked.connect(self._deploy_and_update)

        # Portal preview signals
        self.portal_preview.content_changed.connect(self._on_portal_content_changed)

    def _check_auth_and_load(self) -> None:
        """Check authentication and load initial data."""
        self.status_bar.start_operation("Checking Azure authentication...")

        if not self.auth_service.validate_authentication():
            self.status_bar.show_error("Authentication failed")
            self._show_auth_error()
            return

        self.status_bar.set_status("Authenticated", "success")
        self._refresh_models()

    def _show_auth_error(self) -> None:
        """Show authentication error dialog."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Authentication Required")
        msg.setText("Azure authentication failed.")
        msg.setInformativeText(
            "Please ensure you are logged in to Azure CLI:\n\n"
            "  az login\n\n"
            "Then restart this application."
        )
        msg.setDetailedText(self.auth_service.auth_error or "Unknown error")
        msg.exec()

    def _on_model_selected(self, model: Optional[CatalogModel]) -> None:
        """Handle model selection."""
        self.model_details.set_model(model)

        # Enable/disable delete button based on selection
        if model and model.is_deployed:
            self.delete_btn.setEnabled(True)
        else:
            self.delete_btn.setEnabled(False)

    def _on_selection_changed(self) -> None:
        """Handle checkbox selection changes."""
        checked = self.model_browser.get_checked_models()
        has_checked = len(checked) > 0

        self.deploy_btn.setEnabled(has_checked)
        self.deploy_and_update_btn.setEnabled(has_checked)

        # Update deployment panel with suggested name if single selection
        if len(checked) == 1:
            model = checked[0]
            settings = self.deployment_panel.get_settings()
            suggested_name = settings.get_deployment_name_for_model(model.name, model.version)
            self.deployment_panel.set_deployment_name(suggested_name)

            # Update available SKUs based on model
            if model.available_skus:
                self.deployment_panel.set_available_skus(model.available_skus)
            else:
                self.deployment_panel.reset_skus_to_default()
        else:
            self.deployment_panel.clear_deployment_name()
            self.deployment_panel.reset_skus_to_default()

    def _on_portal_content_changed(self) -> None:
        """Handle portal content changes."""
        # Could save descriptions to config here
        pass

    def _refresh_models(self) -> None:
        """Refresh model list from Azure."""
        if self._refresh_worker and self._refresh_worker.isRunning():
            return

        self.status_bar.start_operation("Loading models from Azure...")
        self._set_ui_enabled(False)

        self._refresh_worker = RefreshWorker(
            self.catalog_service,
            self.deployment_service
        )
        self._refresh_worker.finished.connect(self._on_refresh_finished)
        self._refresh_worker.start()

    def _on_refresh_finished(self, success: bool, message: str, models: list) -> None:
        """Handle refresh completion."""
        self._set_ui_enabled(True)

        if success:
            self.model_browser.populate(models)
            self.status_bar.show_success(message)

            # Update portal preview with deployed models
            deployed = self.deployment_service.get_deployed_models_dict()
            self.portal_preview.populate(deployed, self.config.model_descriptions)

            # Check if portal publish was requested after deployment
            if hasattr(self, '_publish_after_refresh') and self._publish_after_refresh:
                self._publish_after_refresh = False
                # Small delay to let UI update, then start portal publish
                QTimer.singleShot(500, self._start_portal_publish)
        else:
            self.status_bar.show_error(f"Failed to load models: {message}")
            QMessageBox.warning(
                self,
                "Load Failed",
                f"Failed to load models from Azure:\n\n{message}"
            )
            if hasattr(self, '_publish_after_refresh'):
                self._publish_after_refresh = False

    def _deploy_selected(self) -> None:
        """Deploy selected models."""
        models = self.model_browser.get_checked_models()
        if not models:
            return

        # Confirm deployment
        model_names = "\n".join(f"  - {m.name}" for m in models)
        reply = QMessageBox.question(
            self,
            "Confirm Deployment",
            f"Deploy the following {len(models)} model(s)?\n\n{model_names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_deployment(models)

    def _start_deployment(self, models: List[CatalogModel]) -> None:
        """Start deployment worker."""
        if self._deployment_worker and self._deployment_worker.isRunning():
            return

        self.status_bar.start_operation(f"Deploying {len(models)} model(s)...")
        self._set_ui_enabled(False)

        settings = self.deployment_panel.get_settings()

        self._deployment_worker = DeploymentWorker(
            self.deployment_service,
            models,
            settings
        )
        self._deployment_worker.progress.connect(self._on_deployment_progress)
        self._deployment_worker.finished.connect(self._on_deployment_finished)
        self._deployment_worker.start()

    def _on_deployment_progress(self, percent: int, message: str) -> None:
        """Handle deployment progress update."""
        self.status_bar.set_progress(percent, message)

    def _on_deployment_finished(self, success: bool, message: str) -> None:
        """Handle deployment completion."""
        self._set_ui_enabled(True)

        if success:
            self.status_bar.show_success(message)
            self.model_browser.clear_checked()

            # Check if portal update was requested
            if hasattr(self, '_pending_portal_update') and self._pending_portal_update:
                self._pending_portal_update = False
                # Refresh first, then publish portal
                self._refresh_models()
                # Schedule portal publish after refresh (will be triggered by refresh completion)
                self._publish_after_refresh = True
            else:
                self._refresh_models()  # Refresh to show new deployments
        else:
            self.status_bar.show_error(f"Deployment failed: {message}")
            QMessageBox.critical(
                self,
                "Deployment Failed",
                f"Model deployment failed:\n\n{message}"
            )
            if hasattr(self, '_pending_portal_update'):
                self._pending_portal_update = False

    def _delete_deployment(self) -> None:
        """Delete the selected deployment."""
        model = self.model_browser.get_selected_model()
        if not model or not model.is_deployed:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete deployment '{model.deployment_name}'?\n\n"
            f"This will remove the model from your AI Services account.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.start_operation(f"Deleting {model.deployment_name}...")
        self._set_ui_enabled(False)

        try:
            self.deployment_service.delete_deployment(model.deployment_name)
            self.status_bar.show_success(f"Deleted {model.deployment_name}")
            self._refresh_models()
        except Exception as e:
            self.status_bar.show_error(f"Delete failed: {e}")
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete deployment:\n\n{e}"
            )
        finally:
            self._set_ui_enabled(True)

    def _update_portal(self) -> None:
        """Update the Developer Portal with current model list."""
        # Confirm before publishing
        reply = QMessageBox.question(
            self,
            "Confirm Portal Update",
            "Update the Developer Portal with current model list and publish?\n\n"
            "This will make changes live on your portal.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_portal_publish()

    def _start_portal_publish(self) -> None:
        """Start the portal publishing process."""
        if self._portal_worker and self._portal_worker.isRunning():
            return

        # Get models with edited descriptions from preview
        models = self.portal_preview.get_deployed_models_with_descriptions()
        custom_text = self.portal_preview.get_models_text()

        # Save descriptions to config
        descriptions = self.portal_preview.get_descriptions_dict()
        self.config.update_model_descriptions(descriptions)

        # Start publishing state
        self._set_ui_enabled(False)
        self._original_button_text = self.update_portal_btn.text()
        self.update_portal_btn.setText("Publishing...")
        self.update_portal_btn.setEnabled(True)  # Keep visible but show state
        self._start_button_blink(self.update_portal_btn)
        self.status_bar.start_operation("Publishing to Developer Portal...")

        # Start worker
        self._portal_worker = PortalPublishWorker(
            self.portal_service,
            models,
            custom_text
        )
        self._portal_worker.progress.connect(self._on_portal_progress)
        self._portal_worker.finished.connect(self._on_portal_publish_finished)
        self._portal_worker.start()

    def _on_portal_progress(self, message: str) -> None:
        """Handle portal publish progress update."""
        self.status_bar.set_status(message, "working")

    def _on_portal_publish_finished(self, success: bool, message: str) -> None:
        """Handle portal publish completion."""
        self._stop_button_blink()

        if success:
            # Show "Published!" briefly
            self.update_portal_btn.setText("Published!")
            self.update_portal_btn.setStyleSheet(
                "background-color: #9DA03C; color: white;"  # Moss green success
            )
            self.status_bar.show_success(message)

            # Reset button after 2 seconds
            QTimer.singleShot(2000, self._reset_portal_button)
        else:
            self.update_portal_btn.setText("Failed")
            self.update_portal_btn.setStyleSheet(
                "background-color: #C44536; color: white;"  # Error red
            )
            self.status_bar.show_error(f"Portal update failed: {message}")
            QMessageBox.critical(
                self,
                "Publish Failed",
                f"Failed to publish Developer Portal:\n\n{message}"
            )
            # Reset button after 2 seconds
            QTimer.singleShot(2000, self._reset_portal_button)

    def _reset_portal_button(self) -> None:
        """Reset portal button to original state."""
        self.update_portal_btn.setText(self._original_button_text or "Update Portal")
        self.update_portal_btn.setStyleSheet("")  # Reset to default style
        self._set_ui_enabled(True)

    def _start_button_blink(self, button: QPushButton) -> None:
        """Start blinking animation on a button."""
        self._blink_button = button
        self._blink_state = False
        self._blink_timer.start(500)  # Blink every 500ms

    def _stop_button_blink(self) -> None:
        """Stop the button blink animation."""
        self._blink_timer.stop()
        if hasattr(self, '_blink_button'):
            self._blink_button.setStyleSheet("")

    def _toggle_button_blink(self) -> None:
        """Toggle button blink state."""
        if not hasattr(self, '_blink_button'):
            return

        self._blink_state = not self._blink_state
        if self._blink_state:
            self._blink_button.setStyleSheet(
                "background-color: #E6A817; color: white;"  # Warning yellow
            )
        else:
            self._blink_button.setStyleSheet(
                "background-color: #486D87; color: white;"  # Primary blue
            )

    def _deploy_and_update(self) -> None:
        """Deploy selected models and update portal."""
        models = self.model_browser.get_checked_models()
        if not models:
            return

        # Confirm
        model_names = "\n".join(f"  - {m.name}" for m in models)
        reply = QMessageBox.question(
            self,
            "Confirm Deploy & Update",
            f"Deploy the following models and update the Developer Portal?\n\n{model_names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Start deployment - portal update will happen after refresh
        self._start_deployment(models)
        self._pending_portal_update = True

    def _set_ui_enabled(self, enabled: bool) -> None:
        """Enable or disable UI elements during operations."""
        self.model_browser.setEnabled(enabled)
        self.deployment_panel.set_enabled(enabled)
        self.deploy_btn.setEnabled(enabled and len(self.model_browser.get_checked_models()) > 0)
        self.delete_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.update_portal_btn.setEnabled(enabled)
        self.deploy_and_update_btn.setEnabled(enabled and len(self.model_browser.get_checked_models()) > 0)

    def closeEvent(self, event) -> None:
        """Handle window close."""
        # Wait for workers to finish
        if self._deployment_worker and self._deployment_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Deployment in Progress",
                "A deployment is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        if self._refresh_worker and self._refresh_worker.isRunning():
            self._refresh_worker.wait(1000)

        event.accept()
