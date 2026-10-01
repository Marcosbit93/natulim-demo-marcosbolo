from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    shopify_shop: str  # ej.: mi-tienda.myshopify.com
    shopify_client_id: str
    shopify_client_secret: SecretStr
    shopify_api_version: str = "2026-07"

    odoo_url: str = "http://localhost:8069"
    odoo_db: str = "odoo19"
    odoo_api_key: SecretStr