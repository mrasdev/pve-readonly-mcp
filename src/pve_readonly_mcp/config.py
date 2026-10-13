import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    url: str  # e.g. https://pve.local:8006
    token_id: str  # e.g. mcp@pve!readonly
    token_secret: str
    ca_file: str | None = None

    @property
    def base_url(self) -> str:
        return self.url.rstrip("/") + "/api2/json"


def load_settings() -> Settings:
    # .env is optional; real environment variables take precedence
    load_dotenv(override=False)
    try:
        return Settings(
            url=os.environ["PVE_URL"],
            token_id=os.environ["PVE_TOKEN_ID"],
            token_secret=os.environ["PVE_TOKEN_SECRET"],
            ca_file=os.environ.get("PVE_CA_FILE"),
        )
    except KeyError as e:
        raise RuntimeError(f"Environment variable {e.args[0]} is not set") from None
