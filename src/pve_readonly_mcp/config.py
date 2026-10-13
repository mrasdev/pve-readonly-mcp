import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    url: str  # z. B. https://pve.local:8006
    token_id: str  # z. B. mcp@pve!readonly
    token_secret: str
    ca_file: str | None = None

    @property
    def base_url(self) -> str:
        return self.url.rstrip("/") + "/api2/json"


def load_settings() -> Settings:
    load_dotenv(override=False)  # .env optional; echte Umgebungsvariablen gewinnen
    try:
        return Settings(
            url=os.environ["PVE_URL"],
            token_id=os.environ["PVE_TOKEN_ID"],
            token_secret=os.environ["PVE_TOKEN_SECRET"],
            ca_file=os.environ.get("PVE_CA_FILE"),
        )
    except KeyError as e:
        raise RuntimeError(f"Umgebungsvariable {e.args[0]} fehlt") from None
