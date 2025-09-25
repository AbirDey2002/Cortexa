
import os

class PFImageToTextConfigs:
    api_key = os.getenv("PF_API_KEY", "")
    username = os.getenv("PF_USERNAME", "")
    password = os.getenv("PF_PASSWORD", "")
    asset_id = os.getenv("PF_ASSET_ID", "")


