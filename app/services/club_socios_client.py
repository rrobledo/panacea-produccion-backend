from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class SocioInfo:
    categoria: str | None
    puntos: int | None
    fecha_alta: date | None


class ClubSociosClient(Protocol):
    async def fetch_socio(self, socio_id: str) -> SocioInfo | None:
        """Returns the member's current state, or None if not found."""
        ...


class StubClubSociosClient:
    """Placeholder implementation used until the real Club de Socios API
    contract is confirmed (see design.md Open Questions). Always reports
    "not found" rather than raising, so callers (the refresh job) degrade
    gracefully instead of failing outright.
    """

    async def fetch_socio(self, socio_id: str) -> SocioInfo | None:
        return None


def get_club_socios_client() -> ClubSociosClient:
    return StubClubSociosClient()
