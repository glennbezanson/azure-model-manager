# Azure AI Model Manager

A PyQt6 desktop application for managing Azure AI model deployments and updating the APIM Developer Portal with current model information.

## Features

- **Browse Model Catalog**: View all available models in the Azure AI model catalog for your region
- **View Deployments**: See which models are currently deployed to your AI Services account
- **Deploy Models**: Select and deploy new models with configurable settings (capacity, content filter)
- **Update Developer Portal**: Automatically update the APIM Developer Portal with current model list

## Prerequisites

- Python 3.9 or higher
- Azure CLI installed and logged in (`az login`)
- Access to an Azure subscription with:
  - Azure AI Services account
  - Azure API Management instance (optional, for portal updates)

## Installation

1. Clone or download this repository

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example configuration:
   ```bash
   cp config.example.json config.json
   ```

4. Edit `config.json` with your Azure resource details:
   ```json
   {
     "azure": {
       "subscription_id": "your-subscription-id",
       "resource_group": "your-resource-group",
       "ai_services_account": "your-ai-services-account",
       "apim_name": "your-apim-name",
       "location": "eastus2"
     }
   }
   ```

## Usage

1. Ensure you're logged in to Azure CLI:
   ```bash
   az login
   ```

2. Run the application:
   ```bash
   python main.py
   ```

### Deploying Models

1. In the **Model Browser** (left panel), check the boxes next to models you want to deploy
2. Configure deployment settings:
   - **Deployment Name**: Custom name or auto-generated
   - **Capacity (TPM)**: Tokens per minute quota
   - **Content Filter**: Safety filter policy
   - **SKU**: Deployment type (Standard, ProvisionedManaged, etc.)
3. Click **Deploy Selected**

### Updating the Developer Portal

1. After deploying models, review the **Portal Preview** section
2. Edit model descriptions as needed (these will be shown on the portal)
3. Click **Update Portal** to push changes to the Developer Portal

### Deploy & Update in One Action

Click **Deploy & Update Portal** to deploy selected models and automatically update the portal after deployment completes.

## Configuration

### config.json

| Section | Key | Description |
|---------|-----|-------------|
| `azure` | `subscription_id` | Azure subscription ID |
| `azure` | `resource_group` | Resource group containing AI Services |
| `azure` | `ai_services_account` | AI Services account name |
| `azure` | `apim_name` | API Management instance name |
| `azure` | `location` | Azure region (e.g., eastus2) |
| `defaults` | `capacity_tpm` | Default capacity in tokens per minute |
| `defaults` | `content_filter` | Default content filter policy |
| `portal` | `product_id` | APIM product ID for portal updates |
| `portal` | `auto_publish` | Auto-publish portal after updates |
| `portal` | `endpoint_url` | API endpoint URL for portal |
| `model_descriptions` | | Custom descriptions for models |

### Model Descriptions

You can customize how models appear on the Developer Portal by editing the `model_descriptions` section in `config.json`:

```json
{
  "model_descriptions": {
    "gpt-4o": "Most capable GPT-4 model with vision",
    "gpt-4o-mini": "Fast and affordable for simple tasks",
    "my-custom-deployment": "Custom deployment description"
  }
}
```

## Project Structure

```
azure-model-manager/
├── main.py                    # Application entry point
├── config.json                # User configuration
├── config.example.json        # Example configuration
├── requirements.txt           # Python dependencies
├── README.md                  # This file
│
├── ui/                        # User interface components
│   ├── main_window.py         # Main application window
│   ├── model_browser.py       # Model list tree widget
│   ├── model_details.py       # Model details panel
│   ├── deployment_panel.py    # Deployment settings
│   ├── portal_preview.py      # Portal content preview
│   └── status_bar.py          # Status and progress
│
├── services/                  # Azure service integrations
│   ├── azure_auth.py          # Authentication
│   ├── config_manager.py      # Configuration management
│   ├── model_catalog.py       # Model catalog API
│   ├── deployments.py         # Deployment management
│   └── apim_portal.py         # Portal updates
│
├── models/                    # Data models
│   ├── catalog_model.py       # Catalog model dataclass
│   └── deployment.py          # Deployment dataclass
│
└── resources/                 # Application resources
    └── icon.ico               # Application icon (optional)
```

## Troubleshooting

### Authentication Failed

Ensure Azure CLI is logged in:
```bash
az login
az account show  # Verify correct subscription
az account set --subscription "your-subscription-id"  # If needed
```

### Models Not Loading

- Verify your AI Services account exists and you have access
- Check that the location in config matches your account's region
- Ensure your Azure account has the necessary permissions

### Deployment Fails

- Check quota availability in your subscription
- Verify the model is available in your region
- Ensure the content filter policy exists

### Portal Update Fails

- Verify APIM instance name is correct
- Ensure the product ID exists in your APIM
- Check that you have contributor access to APIM

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Building Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

## License

Internal use only - Edge Solutions
