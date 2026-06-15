"""Собирает secrets для локального запуска и Streamlit Cloud."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "service-account.json"
LOCAL_SECRETS = ROOT / ".streamlit" / "secrets.toml"
CLOUD_SECRETS = ROOT / "streamlit-cloud-secrets.toml"
SPREADSHEET_ID = "14ecZy9BRnYiHOjASyPmcBttuUjtv6rY-a4cazeBhldM"


def build_toml(data: dict, *, ssl_verify: bool) -> str:
    private_key = data["private_key"].replace("\\n", "\n").strip()
    ssl_value = "true" if ssl_verify else "false"
    return f"""[gcp_service_account]
type = "{data['type']}"
project_id = "{data['project_id']}"
private_key_id = "{data['private_key_id']}"
client_email = "{data['client_email']}"
client_id = "{data['client_id']}"
auth_uri = "{data['auth_uri']}"
token_uri = "{data['token_uri']}"
auth_provider_x509_cert_url = "{data['auth_provider_x509_cert_url']}"
client_x509_cert_url = "{data['client_x509_cert_url']}"
universe_domain = "{data['universe_domain']}"

private_key = \"\"\"
{private_key}
\"\"\"

[references]
spreadsheet_id = "{SPREADSHEET_ID}"
ssl_verify = {ssl_value}
"""


def main() -> None:
    if not JSON_PATH.is_file():
        raise SystemExit(f"Не найден {JSON_PATH}")

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    local_toml = build_toml(data, ssl_verify=False)
    LOCAL_SECRETS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SECRETS.write_text(local_toml, encoding="utf-8")
    print(f"Локально: {LOCAL_SECRETS}")

    cloud_toml = build_toml(data, ssl_verify=True)
    CLOUD_SECRETS.write_text(cloud_toml, encoding="utf-8")
    print(f"Dlya Streamlit Cloud (skopiruyte v Settings -> Secrets): {CLOUD_SECRETS}")
    print()
    print("Streamlit Cloud: Manage app -> Settings -> Secrets -> vstavte soderzhimoe")
    print(f"fayla {CLOUD_SECRETS.name} -> Save -> Reboot app.")


if __name__ == "__main__":
    main()
