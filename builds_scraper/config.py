"""Runtime configuration. Override any field via environment / .env (see .env.example)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUILDS_", env_file=".env", extra="ignore")

    # League to scrape (the poe.ninja slug, e.g. "runesofaldur").
    league_slug: str = "runesofaldur"

    # poe.ninja base. The /search and /character endpoints are gated by a browser-like
    # request: a normal User-Agent plus a Referer to the builds page. No auth/cookies.
    poeninja_base: str = "https://poe.ninja/poe2/api"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    # Used in the GGG-required disclaimer and as a courtesy contact.
    contact_email: str = "frankiebraybon@gmail.com"

    # Politeness. poe.ninja publishes no rate limit; we self-throttle.
    request_delay_s: float = 0.5  # min seconds between per-character requests
    timeout_s: float = 30.0
    max_retries: int = 4

    # How many of the top builds to pull per run. The /search endpoint returns ~100.
    roster_limit: int = 100

    # Paths
    cache_dir: Path = Field(default=REPO_ROOT / "cache")  # gitignored: raw per-char JSON + versioned archives
    output_dir: Path = Field(default=REPO_ROOT / "output")  # gitignored: versioned artifacts (local runs)
    published_dir: Path = Field(default=REPO_ROOT / "data")  # COMMITTED: latest-<slug>.json the app fetches

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "characters").mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.published_dir.mkdir(parents=True, exist_ok=True)
