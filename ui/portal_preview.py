"""Portal preview panel for Azure Model Manager."""
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QGroupBox, QHeaderView, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal


class PortalPreviewPanel(QWidget):
    """Editable preview of the portal models list."""

    # Signals
    content_changed = pyqtSignal()  # Emitted when user edits descriptions

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._models: List[Dict[str, str]] = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("Portal Preview (editable)")
        layout = QVBoxLayout(group)

        # Header with instructions
        header_layout = QHBoxLayout()
        header_label = QLabel(
            "Edit descriptions below. These will be shown on the Developer Portal."
        )
        header_label.setStyleSheet("color: gray; font-style: italic;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        # Reset button
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setToolTip("Reset descriptions to defaults")
        self.reset_btn.setMaximumWidth(80)
        header_layout.addWidget(self.reset_btn)

        layout.addLayout(header_layout)

        # Table for model descriptions
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Deployment Name", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setMinimumHeight(150)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Preview text
        preview_label = QLabel("Preview text that will be pushed to portal:")
        preview_label.setStyleSheet("margin-top: 10px; font-weight: bold;")
        layout.addWidget(preview_label)

        self.preview_text = QLabel()
        self.preview_text.setWordWrap(True)
        self.preview_text.setStyleSheet(
            "background-color: #f5f5f5; padding: 10px; border: 1px solid #ddd; "
            "border-radius: 4px; font-family: monospace;"
        )
        self.preview_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.preview_text)

        main_layout.addWidget(group)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.table.cellChanged.connect(self._on_cell_changed)
        self.reset_btn.clicked.connect(self._on_reset_clicked)

    def populate(
        self,
        deployed_models: List[Dict[str, str]],
        descriptions: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Populate table with deployed models and their descriptions.

        Args:
            deployed_models: List of dicts with deployment_name, model_name, description
            descriptions: Optional dict of deployment_name -> description overrides
        """
        descriptions = descriptions or {}
        self._models = deployed_models

        # Block signals during population
        self.table.blockSignals(True)
        self.table.setRowCount(len(deployed_models))

        for i, model in enumerate(deployed_models):
            name = model.get("deployment_name", "")

            # Deployment name (read-only)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(f"Model: {model.get('model_name', 'Unknown')}")
            self.table.setItem(i, 0, name_item)

            # Description (editable)
            desc = descriptions.get(name) or model.get("description", "")
            desc_item = QTableWidgetItem(desc)
            self.table.setItem(i, 1, desc_item)

        self.table.blockSignals(False)
        self._update_preview()

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Handle cell changes."""
        if col == 1:  # Description column
            self._update_preview()
            self.content_changed.emit()

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        # Repopulate with original model descriptions
        self.table.blockSignals(True)
        for i, model in enumerate(self._models):
            desc = model.get("description", model.get("model_name", ""))
            desc_item = self.table.item(i, 1)
            if desc_item:
                desc_item.setText(desc)
        self.table.blockSignals(False)
        self._update_preview()
        self.content_changed.emit()

    def _update_preview(self) -> None:
        """Update the preview text."""
        preview = self.get_models_text()
        self.preview_text.setText(preview)

    def get_models_text(self) -> str:
        """
        Generate the text that will be pushed to the portal.

        Returns:
            Formatted text - one model name per line
        """
        if self.table.rowCount() == 0:
            return "No models currently deployed"

        # Simple format: one model name per line
        lines = []

        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)

            if name_item:
                name = name_item.text()
                if name:
                    lines.append(name)

        return "\n".join(lines)

    def get_descriptions_dict(self) -> Dict[str, str]:
        """
        Get current descriptions as dict for saving to config.

        Returns:
            Dict mapping deployment names to descriptions
        """
        result = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            desc_item = self.table.item(row, 1)

            if name_item and desc_item:
                name = name_item.text()
                desc = desc_item.text()
                if desc:
                    result[name] = desc

        return result

    def get_deployed_models_with_descriptions(self) -> List[Dict[str, str]]:
        """
        Get deployed models with current (possibly edited) descriptions.

        Returns:
            List of dicts with deployment_name and description
        """
        result = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            desc_item = self.table.item(row, 1)

            if name_item and desc_item:
                result.append({
                    "deployment_name": name_item.text(),
                    "description": desc_item.text()
                })

        return result

    def set_description(self, deployment_name: str, description: str) -> None:
        """
        Set description for a specific deployment.

        Args:
            deployment_name: The deployment name
            description: The description to set
        """
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item and name_item.text() == deployment_name:
                desc_item = self.table.item(row, 1)
                if desc_item:
                    desc_item.setText(description)
                    self._update_preview()
                break

    def clear(self) -> None:
        """Clear the table."""
        self.table.setRowCount(0)
        self._models = []
        self._update_preview()

    def has_changes(self) -> bool:
        """
        Check if descriptions have been modified from original.

        Returns:
            True if any descriptions differ from original
        """
        for i, model in enumerate(self._models):
            if i >= self.table.rowCount():
                break
            desc_item = self.table.item(i, 1)
            if desc_item:
                original = model.get("description", "")
                current = desc_item.text()
                if original != current:
                    return True
        return False
