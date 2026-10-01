from natulim_demo_marcosbolo.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "demo.myshopify.com")
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "mi_clave_secreta")
    monkeypatch.setenv("ODOO_API_KEY", "key")

    s = Settings(_env_file=None)
    assert s.shopify_api_version == "2026-07"
    assert s.shopify_client_secret.get_secret_value() == "mi_clave_secreta"
    assert "mi_clave_secreta" not in repr(s)