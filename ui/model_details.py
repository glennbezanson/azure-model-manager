"""Model details panel for Azure Model Manager."""
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextBrowser, QGroupBox, QGridLayout,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt

from models.catalog_model import CatalogModel


class ModelDetailsPanel(QWidget):
    """Panel displaying detailed information about a selected model."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_model: Optional[CatalogModel] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Main layout for this widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Create container widget for scroll area
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(12)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        self.header_label = QLabel("Select a model to view details")
        self.header_label.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px 0;")
        layout.addWidget(self.header_label)

        # Basic info group
        info_group = QGroupBox("Model Information")
        info_layout = QGridLayout(info_group)
        info_layout.setVerticalSpacing(10)
        info_layout.setHorizontalSpacing(15)
        info_layout.setContentsMargins(12, 15, 12, 12)

        # Style for field labels (bold)
        label_style = "font-weight: bold; color: #555;"
        value_style = "padding: 2px 0;"

        # Labels for model info
        self.name_label = QLabel("-")
        self.name_label.setStyleSheet(value_style)
        self.version_label = QLabel("-")
        self.version_label.setStyleSheet(value_style)
        self.publisher_label = QLabel("-")
        self.publisher_label.setStyleSheet(value_style)
        self.format_label = QLabel("-")
        self.format_label.setStyleSheet(value_style)
        self.status_label = QLabel("-")
        self.status_label.setStyleSheet(value_style)

        name_lbl = QLabel("Name:")
        name_lbl.setStyleSheet(label_style)
        version_lbl = QLabel("Version:")
        version_lbl.setStyleSheet(label_style)
        publisher_lbl = QLabel("Publisher:")
        publisher_lbl.setStyleSheet(label_style)
        format_lbl = QLabel("Format:")
        format_lbl.setStyleSheet(label_style)
        status_lbl = QLabel("Status:")
        status_lbl.setStyleSheet(label_style)

        info_layout.addWidget(name_lbl, 0, 0)
        info_layout.addWidget(self.name_label, 0, 1)
        info_layout.addWidget(version_lbl, 0, 2)
        info_layout.addWidget(self.version_label, 0, 3)

        info_layout.addWidget(publisher_lbl, 1, 0)
        info_layout.addWidget(self.publisher_label, 1, 1)
        info_layout.addWidget(format_lbl, 1, 2)
        info_layout.addWidget(self.format_label, 1, 3)

        info_layout.addWidget(status_lbl, 2, 0)
        info_layout.addWidget(self.status_label, 2, 1, 1, 3)

        info_layout.setColumnStretch(1, 1)
        info_layout.setColumnStretch(3, 1)
        layout.addWidget(info_group)

        # Capabilities group
        caps_group = QGroupBox("Capabilities")
        caps_layout = QVBoxLayout(caps_group)
        caps_layout.setContentsMargins(12, 15, 12, 12)
        caps_layout.setSpacing(8)
        self.capabilities_label = QLabel("-")
        self.capabilities_label.setWordWrap(True)
        self.capabilities_label.setStyleSheet("line-height: 1.5;")
        caps_layout.addWidget(self.capabilities_label)
        layout.addWidget(caps_group)

        # Technical specs group
        specs_group = QGroupBox("Technical Specifications")
        specs_layout = QGridLayout(specs_group)
        specs_layout.setVerticalSpacing(10)
        specs_layout.setHorizontalSpacing(15)
        specs_layout.setContentsMargins(12, 15, 12, 12)

        self.context_label = QLabel("-")
        self.context_label.setStyleSheet(value_style)
        self.output_label = QLabel("-")
        self.output_label.setStyleSheet(value_style)
        self.deprecation_label = QLabel("-")
        self.deprecation_label.setStyleSheet(value_style)
        self.skus_label = QLabel("-")
        self.skus_label.setStyleSheet(value_style)

        context_lbl = QLabel("Context Window:")
        context_lbl.setStyleSheet(label_style)
        output_lbl = QLabel("Max Output:")
        output_lbl.setStyleSheet(label_style)
        deprecation_lbl = QLabel("Deprecation:")
        deprecation_lbl.setStyleSheet(label_style)
        skus_lbl = QLabel("SKUs:")
        skus_lbl.setStyleSheet(label_style)

        specs_layout.addWidget(context_lbl, 0, 0)
        specs_layout.addWidget(self.context_label, 0, 1)
        specs_layout.addWidget(output_lbl, 0, 2)
        specs_layout.addWidget(self.output_label, 0, 3)

        specs_layout.addWidget(deprecation_lbl, 1, 0)
        specs_layout.addWidget(self.deprecation_label, 1, 1)
        specs_layout.addWidget(skus_lbl, 1, 2)
        specs_layout.addWidget(self.skus_label, 1, 3)

        specs_layout.setColumnStretch(1, 1)
        specs_layout.setColumnStretch(3, 1)
        layout.addWidget(specs_group)

        # Description
        desc_group = QGroupBox("Description")
        desc_layout = QVBoxLayout(desc_group)
        desc_layout.setContentsMargins(12, 15, 12, 12)
        self.description_browser = QTextBrowser()
        self.description_browser.setOpenExternalLinks(True)
        self.description_browser.setMinimumHeight(120)
        desc_layout.addWidget(self.description_browser)
        layout.addWidget(desc_group)

        # Stretch at bottom
        layout.addStretch()

        # Set scroll area content and add to main layout
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def set_model(self, model: Optional[CatalogModel]) -> None:
        """
        Set the model to display.

        Args:
            model: CatalogModel to display, or None to clear
        """
        self._current_model = model

        if model is None:
            self._clear_display()
            return

        # Update header
        self.header_label.setText(model.display_name)

        # Update basic info
        self.name_label.setText(model.name or "N/A")
        self.version_label.setText(model.version or "N/A")
        self.publisher_label.setText(model.publisher if model.publisher and model.publisher != "None" else model.model_format or "N/A")
        self.format_label.setText(model.model_format or "N/A")

        # Status
        if model.is_deployed:
            self.status_label.setText(f"<span style='color: green;'>Deployed as '{model.deployment_name}'</span>")
        elif model.is_deprecated:
            self.status_label.setText("<span style='color: red;'>Deprecated</span>")
        else:
            self.status_label.setText("<span style='color: blue;'>Available</span>")

        # Capabilities
        if model.capabilities:
            caps_formatted = []
            for cap in model.capabilities:
                cap_display = cap.replace("_", " ").title()
                caps_formatted.append(f"\u2022 {cap_display}")
            self.capabilities_label.setText("\n".join(caps_formatted))
        else:
            self.capabilities_label.setText("Not specified")

        # Technical specs
        if model.context_window > 0:
            self.context_label.setText(f"{model.context_window:,} tokens")
        else:
            self.context_label.setText("Not specified")

        if model.max_output_tokens > 0:
            self.output_label.setText(f"{model.max_output_tokens:,} tokens")
        else:
            self.output_label.setText("Not specified")

        if model.deprecation_date:
            self.deprecation_label.setText(f"<span style='color: orange;'>{model.deprecation_date}</span>")
        else:
            self.deprecation_label.setText("None")

        if model.available_skus:
            self.skus_label.setText(", ".join(model.available_skus))
        else:
            self.skus_label.setText("Standard")

        # Description
        description_html = f"<p>{model.description}</p>" if model.description else "<p><i>No description available</i></p>"
        if model.regions:
            description_html += f"<p><b>Available in:</b> {', '.join(model.regions)}</p>"
        self.description_browser.setHtml(description_html)

    def _clear_display(self) -> None:
        """Clear all displayed information."""
        self.header_label.setText("Select a model to view details")
        self.name_label.setText("-")
        self.version_label.setText("-")
        self.publisher_label.setText("-")
        self.format_label.setText("-")
        self.status_label.setText("-")
        self.capabilities_label.setText("-")
        self.context_label.setText("-")
        self.output_label.setText("-")
        self.deprecation_label.setText("-")
        self.skus_label.setText("-")
        self.description_browser.setHtml("")

    def get_current_model(self) -> Optional[CatalogModel]:
        """
        Get the currently displayed model.

        Returns:
            Current CatalogModel or None
        """
        return self._current_model

    def refresh(self) -> None:
        """Refresh the display with current model data."""
        if self._current_model:
            self.set_model(self._current_model)
