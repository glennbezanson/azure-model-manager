"""Status bar widget for Azure Model Manager."""
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt


class StatusBar(QWidget):
    """Status bar with message and progress indicator."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    # Edge Solutions Brand Colors
    COLOR_PRIMARY = "#486D87"      # Edge Blue
    COLOR_SUCCESS = "#9DA03C"      # Moss Green (visible success)
    COLOR_WARNING = "#E6A817"      # Warning
    COLOR_ERROR = "#C44536"        # Error
    COLOR_MUTED = "#7B7D72"        # Olive Gray

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Create a frame for styling
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setObjectName("statusFrame")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.addWidget(frame)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)

        # Status icon/indicator
        self.status_indicator = QLabel("\u25cf")  # Circle
        self.status_indicator.setStyleSheet(f"color: {self.COLOR_SUCCESS}; font-size: 12px;")
        self.status_indicator.setFixedWidth(24)
        layout.addWidget(self.status_indicator)

        # Status message
        self.status_label = QLabel("Ready")
        self.status_label.setMinimumWidth(200)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.hide()  # Hidden by default
        layout.addWidget(self.progress_bar)

        # Percentage label (shown when progress bar is visible)
        self.percent_label = QLabel("")
        self.percent_label.setMinimumWidth(50)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.percent_label.hide()
        layout.addWidget(self.percent_label)

    def set_status(self, message: str, status_type: str = "info") -> None:
        """
        Set the status message.

        Args:
            message: Status message to display
            status_type: Type of status ("info", "success", "warning", "error", "working")
        """
        self.status_label.setText(message)

        # Update indicator color based on type (Edge Solutions brand colors)
        colors = {
            "info": self.COLOR_PRIMARY,
            "success": self.COLOR_SUCCESS,
            "warning": self.COLOR_WARNING,
            "error": self.COLOR_ERROR,
            "working": self.COLOR_PRIMARY
        }
        color = colors.get(status_type, self.COLOR_MUTED)
        self.status_indicator.setStyleSheet(f"color: {color}; font-size: 12px;")

        # Use different icon for working state
        if status_type == "working":
            self.status_indicator.setText("\u25cb")  # Empty circle
        elif status_type == "success":
            self.status_indicator.setText("\u2713")  # Checkmark
        elif status_type == "error":
            self.status_indicator.setText("\u2717")  # X mark
        elif status_type == "warning":
            self.status_indicator.setText("\u26a0")  # Warning triangle
        else:
            self.status_indicator.setText("\u25cf")  # Filled circle

    def show_progress(self, visible: bool = True) -> None:
        """
        Show or hide the progress bar.

        Args:
            visible: Whether to show the progress bar
        """
        if visible:
            self.progress_bar.show()
            self.percent_label.show()
        else:
            self.progress_bar.hide()
            self.percent_label.hide()
            self.progress_bar.setValue(0)
            self.percent_label.setText("")

    def set_progress(self, value: int, message: Optional[str] = None) -> None:
        """
        Set the progress bar value.

        Args:
            value: Progress percentage (0-100)
            message: Optional status message to display
        """
        self.progress_bar.setValue(value)
        self.percent_label.setText(f"{value}%")

        if message:
            self.set_status(message, "working")

        # Show progress bar if not visible
        if not self.progress_bar.isVisible():
            self.show_progress(True)

    def set_indeterminate(self, indeterminate: bool = True, message: Optional[str] = None) -> None:
        """
        Set the progress bar to indeterminate mode.

        Args:
            indeterminate: Whether to enable indeterminate mode
            message: Optional status message to display
        """
        if indeterminate:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(0)  # This makes it indeterminate
            self.percent_label.setText("...")
            self.show_progress(True)
            if message:
                self.set_status(message, "working")
        else:
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            self.percent_label.setText("")

    def reset(self) -> None:
        """Reset to default state."""
        self.set_status("Ready", "success")
        self.show_progress(False)

    def show_success(self, message: str) -> None:
        """
        Show a success message.

        Args:
            message: Success message to display
        """
        self.set_status(message, "success")
        self.show_progress(False)

    def show_error(self, message: str) -> None:
        """
        Show an error message.

        Args:
            message: Error message to display
        """
        self.set_status(message, "error")
        self.show_progress(False)

    def show_warning(self, message: str) -> None:
        """
        Show a warning message.

        Args:
            message: Warning message to display
        """
        self.set_status(message, "warning")

    def start_operation(self, message: str) -> None:
        """
        Start showing an operation in progress.

        Args:
            message: Description of the operation
        """
        self.set_status(message, "working")
        self.set_indeterminate(True)

    def finish_operation(self, message: str, success: bool = True) -> None:
        """
        Finish showing an operation.

        Args:
            message: Completion message
            success: Whether the operation succeeded
        """
        if success:
            self.show_success(message)
        else:
            self.show_error(message)
