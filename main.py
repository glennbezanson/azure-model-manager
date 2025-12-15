#!/usr/bin/env python3
"""
Azure AI Model Manager

A PyQt6 desktop application for managing Azure AI model deployments
and updating the APIM Developer Portal.
"""
import sys
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon


def setup_logging() -> None:
    """Configure application logging."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Reduce noise from Azure SDK
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def check_dependencies() -> bool:
    """Check that required dependencies are installed."""
    missing = []

    try:
        import PyQt6
    except ImportError:
        missing.append("PyQt6")

    try:
        import azure.identity
    except ImportError:
        missing.append("azure-identity")

    try:
        import azure.mgmt.cognitiveservices
    except ImportError:
        missing.append("azure-mgmt-cognitiveservices")

    try:
        import azure.mgmt.apimanagement
    except ImportError:
        missing.append("azure-mgmt-apimanagement")

    try:
        import requests
    except ImportError:
        missing.append("requests")

    if missing:
        print(f"Missing required dependencies: {', '.join(missing)}")
        print("\nInstall them with:")
        print(f"  pip install {' '.join(missing)}")
        return False

    return True


def main() -> int:
    """Main application entry point."""
    # Set up logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Check dependencies
    if not check_dependencies():
        return 1

    # Import after dependency check
    from ui.main_window import MainWindow

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Azure AI Model Manager")
    app.setOrganizationName("Edge Solutions")
    app.setOrganizationDomain("edgesolutions.com")

    # Set application style
    app.setStyle("Fusion")

    # Set icon if available
    icon_path = Path(__file__).parent / "resources" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Load Edge Solutions stylesheet
    style_path = Path(__file__).parent / "resources" / "styles.qss"
    if style_path.exists():
        with open(style_path, 'r') as f:
            app.setStyleSheet(f.read())
        logger.info("Loaded Edge Solutions stylesheet")

    try:
        # Create and show main window
        window = MainWindow()
        window.show()

        logger.info("Azure AI Model Manager started")

        # Run event loop
        return app.exec()

    except Exception as e:
        logger.exception("Application error")
        QMessageBox.critical(
            None,
            "Application Error",
            f"An error occurred:\n\n{e}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
