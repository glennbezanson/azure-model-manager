"""Model browser tree widget for Azure Model Manager."""
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal

from models.catalog_model import CatalogModel


class ModelBrowser(QWidget):
    """Tree widget for browsing available and deployed models."""

    # Signals
    model_selected = pyqtSignal(object)  # Emits CatalogModel or None
    selection_changed = pyqtSignal()  # Emits when checkbox selection changes

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._models: List[CatalogModel] = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search/filter box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter models...")
        self.search_box.setClearButtonEnabled(True)
        layout.addWidget(self.search_box)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setIndentation(20)
        layout.addWidget(self.tree)

        # Create category nodes
        self.deployed_node = QTreeWidgetItem(["Deployed Models"])
        self.deployed_node.setFlags(
            self.deployed_node.flags() & ~Qt.ItemFlag.ItemIsSelectable
        )
        self.tree.addTopLevelItem(self.deployed_node)

        self.available_node = QTreeWidgetItem(["Available Models"])
        self.available_node.setFlags(
            self.available_node.flags() & ~Qt.ItemFlag.ItemIsSelectable
        )
        self.tree.addTopLevelItem(self.available_node)

        # Set font for category nodes
        font = self.deployed_node.font(0)
        font.setBold(True)
        self.deployed_node.setFont(0, font)
        self.available_node.setFont(0, font)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        self.search_box.textChanged.connect(self._filter_models)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemChanged.connect(self._on_item_changed)

    def populate(self, models: List[CatalogModel]) -> None:
        """
        Populate the tree with models.

        Args:
            models: List of CatalogModel objects
        """
        self._models = models

        # Block signals during population
        self.tree.blockSignals(True)

        # Clear existing items
        self.deployed_node.takeChildren()
        self.available_node.takeChildren()

        for model in models:
            # Use just the model name (version shown in tooltip/details)
            item = QTreeWidgetItem([model.name])
            item.setData(0, Qt.ItemDataRole.UserRole, model)

            if model.is_deployed:
                # Deployed models get a checkmark indicator (not checkable)
                item.setText(0, f"\u2713 {model.name}")
                item.setToolTip(0, f"Deployed as: {model.deployment_name}\nVersion: {model.version}")
                self.deployed_node.addChild(item)
            else:
                # Available models get a checkbox
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setToolTip(0, f"Version: {model.version}\nPublisher: {model.publisher}")
                self.available_node.addChild(item)

        # Update counts in headers
        deployed_count = self.deployed_node.childCount()
        available_count = self.available_node.childCount()
        self.deployed_node.setText(0, f"Deployed Models ({deployed_count})")
        self.available_node.setText(0, f"Available Models ({available_count})")

        # Expand both sections
        self.deployed_node.setExpanded(True)
        self.available_node.setExpanded(True)

        self.tree.blockSignals(False)

    def _filter_models(self, query: str) -> None:
        """
        Filter visible models based on search query.

        Args:
            query: Search string
        """
        query_lower = query.lower()

        # Filter deployed models
        for i in range(self.deployed_node.childCount()):
            item = self.deployed_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model:
                matches = (
                    query_lower in model.name.lower() or
                    query_lower in model.description.lower() or
                    any(query_lower in cap.lower() for cap in model.capabilities)
                )
                item.setHidden(not matches)

        # Filter available models
        for i in range(self.available_node.childCount()):
            item = self.available_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model:
                matches = (
                    query_lower in model.name.lower() or
                    query_lower in model.description.lower() or
                    any(query_lower in cap.lower() for cap in model.capabilities)
                )
                item.setHidden(not matches)

    def _on_selection_changed(self) -> None:
        """Handle tree selection changes."""
        selected_items = self.tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model:
                self.model_selected.emit(model)
            else:
                self.model_selected.emit(None)
        else:
            self.model_selected.emit(None)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item checkbox changes."""
        if column == 0:
            self.selection_changed.emit()

    def get_selected_model(self) -> Optional[CatalogModel]:
        """
        Get the currently selected model.

        Returns:
            Selected CatalogModel or None
        """
        selected_items = self.tree.selectedItems()
        if selected_items:
            return selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        return None

    def get_checked_models(self) -> List[CatalogModel]:
        """
        Get all models checked for deployment.

        Returns:
            List of CatalogModel objects that are checked
        """
        checked = []
        for i in range(self.available_node.childCount()):
            item = self.available_node.child(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                model = item.data(0, Qt.ItemDataRole.UserRole)
                if model:
                    checked.append(model)
        return checked

    def clear_checked(self) -> None:
        """Uncheck all checked models."""
        self.tree.blockSignals(True)
        for i in range(self.available_node.childCount()):
            item = self.available_node.child(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self.selection_changed.emit()

    def check_model(self, model_name: str, checked: bool = True) -> None:
        """
        Check or uncheck a model by name.

        Args:
            model_name: The model name to check
            checked: Whether to check or uncheck
        """
        for i in range(self.available_node.childCount()):
            item = self.available_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model and model.name.lower() == model_name.lower():
                state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                item.setCheckState(0, state)
                break

    def get_all_models(self) -> List[CatalogModel]:
        """
        Get all models in the browser.

        Returns:
            List of all CatalogModel objects
        """
        return self._models.copy()

    def get_deployed_models(self) -> List[CatalogModel]:
        """
        Get all deployed models.

        Returns:
            List of deployed CatalogModel objects
        """
        deployed = []
        for i in range(self.deployed_node.childCount()):
            item = self.deployed_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model:
                deployed.append(model)
        return deployed

    def select_model(self, model_name: str) -> bool:
        """
        Select a model by name in the tree.

        Args:
            model_name: The model name to select

        Returns:
            True if model was found and selected
        """
        # Check deployed models
        for i in range(self.deployed_node.childCount()):
            item = self.deployed_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model and model.name.lower() == model_name.lower():
                self.tree.setCurrentItem(item)
                return True

        # Check available models
        for i in range(self.available_node.childCount()):
            item = self.available_node.child(i)
            model = item.data(0, Qt.ItemDataRole.UserRole)
            if model and model.name.lower() == model_name.lower():
                self.tree.setCurrentItem(item)
                return True

        return False
