import ssl

import httpx


class PveError(Exception):
    """Error while accessing the Proxmox API."""


class PveClient:
    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        ca_file: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        verify = ssl.create_default_context(cafile=ca_file) if ca_file else True
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"PVEAPIToken={token_id}={token_secret}"},
            verify=verify,
            timeout=10.0,
            transport=transport,
        )

    def get(self, path: str, params: dict | None = None):
        try:
            r = self._http.get(path, params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise PveError(
                f"Proxmox API: HTTP {e.response.status_code} for {path}"
            ) from e
        except httpx.HTTPError as e:
            raise PveError(f"Proxmox API unreachable: {e}") from e
        return r.json()["data"]  # Proxmox wraps every response in {"data": ...}
