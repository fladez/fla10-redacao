"""Configuração carregada do ambiente, sem armazenar segredos no código."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    github_token: str
    editorial_repo: str = "rcorreas/Redacao-Fla10"
    editorial_branch: str = "main"
    github_api_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "GITHUB_TOKEN não definido. Configure a credencial GitHub localmente "
                "conforme docs/10-configuracao-local.md."
            )
        return cls(
            github_token=token,
            editorial_repo=os.getenv("EDITORIAL_REPO", "rcorreas/Redacao-Fla10").strip(),
            editorial_branch=os.getenv("EDITORIAL_BRANCH", "main").strip(),
            github_api_url=os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
        )


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str
    api_url: str = "https://openrouter.ai/api/v1"

    @classmethod
    def from_env(cls) -> "OpenRouterSettings":
        load_dotenv()
        token = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not token:
            raise ValueError(
                "OPENROUTER_API_KEY não definido. Configure a chave localmente no .env; "
                "nunca a envie pelo chat nem a versione no Git."
            )
        return cls(
            api_key=token,
            api_url=os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        )
