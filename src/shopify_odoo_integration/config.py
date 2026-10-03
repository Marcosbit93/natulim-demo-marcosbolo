from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    shopify_shop: str
    shopify_client_id: str
    shopify_client_secret: str
    shopify_api_version: str = "2026-07"
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_api_key: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"