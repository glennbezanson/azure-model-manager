"""Azure authentication service using DefaultAzureCredential."""
import logging
from typing import Optional

from azure.identity import DefaultAzureCredential, AzureCliCredential
from azure.core.exceptions import ClientAuthenticationError

logger = logging.getLogger(__name__)


class AzureAuthService:
    """Handles Azure authentication using DefaultAzureCredential."""

    def __init__(self):
        self._credential: Optional[DefaultAzureCredential] = None
        self._is_authenticated = False
        self._auth_error: Optional[str] = None

    @property
    def credential(self) -> DefaultAzureCredential:
        """Get the Azure credential, initializing if needed."""
        if self._credential is None:
            self._initialize_credential()
        return self._credential

    @property
    def is_authenticated(self) -> bool:
        """Check if we have valid authentication."""
        return self._is_authenticated

    @property
    def auth_error(self) -> Optional[str]:
        """Get the last authentication error message."""
        return self._auth_error

    def _initialize_credential(self) -> None:
        """Initialize the Azure credential."""
        try:
            # DefaultAzureCredential tries multiple auth methods:
            # 1. Environment variables
            # 2. Managed Identity
            # 3. Azure CLI
            # 4. Azure PowerShell
            # 5. Interactive browser
            self._credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=False,
                exclude_visual_studio_code_credential=True  # Can be slow
            )
            logger.info("Azure credential initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Azure credential: {e}")
            self._auth_error = str(e)
            raise

    def validate_authentication(self) -> bool:
        """
        Validate that the credential can authenticate.

        Returns:
            True if authentication is valid, False otherwise.
        """
        try:
            # Try to get a token to validate authentication
            token = self.credential.get_token("https://management.azure.com/.default")
            if token:
                self._is_authenticated = True
                self._auth_error = None
                logger.info("Azure authentication validated successfully")
                return True
        except ClientAuthenticationError as e:
            self._is_authenticated = False
            self._auth_error = f"Authentication failed: {e.message}"
            logger.error(f"Azure authentication failed: {e}")
        except Exception as e:
            self._is_authenticated = False
            self._auth_error = f"Authentication error: {str(e)}"
            logger.error(f"Azure authentication error: {e}")

        return False

    def get_access_token(self, scope: str = "https://management.azure.com/.default") -> Optional[str]:
        """
        Get an access token for the specified scope.

        Args:
            scope: The token scope (default: Azure Management)

        Returns:
            The access token string, or None if failed.
        """
        try:
            token = self.credential.get_token(scope)
            return token.token
        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            self._auth_error = str(e)
            return None

    def refresh_credential(self) -> bool:
        """
        Force refresh of the credential.

        Returns:
            True if refresh successful, False otherwise.
        """
        self._credential = None
        self._is_authenticated = False
        self._auth_error = None

        try:
            self._initialize_credential()
            return self.validate_authentication()
        except Exception as e:
            self._auth_error = str(e)
            return False

    @staticmethod
    def check_azure_cli_logged_in() -> bool:
        """
        Check if Azure CLI is logged in.

        Returns:
            True if Azure CLI is logged in, False otherwise.
        """
        try:
            cli_credential = AzureCliCredential()
            cli_credential.get_token("https://management.azure.com/.default")
            return True
        except Exception:
            return False

    @staticmethod
    def get_auth_instructions() -> str:
        """Get instructions for authenticating with Azure."""
        return """
To authenticate with Azure, you can use one of these methods:

1. Azure CLI (Recommended):
   Run: az login

2. Azure PowerShell:
   Run: Connect-AzAccount

3. Environment Variables:
   Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID

4. Visual Studio Code:
   Sign in to Azure in VS Code

After authenticating, restart this application.
"""
