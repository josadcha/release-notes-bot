from dataclasses import dataclass, field
from typing import List, Optional
import os
import yaml
from dotenv import load_dotenv

# Load .env once at import time
load_dotenv()


@dataclass
class RepoSpec:
    owner: str
    name: str
    since_ref: Optional[str] = None
    until_ref: Optional[str] = None
    since_date: Optional[str] = None  # ISO date

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass
class LLMConfig:
    provider: str = "openai"
    model: str = "gpt-5"
    max_tokens: int = 2000
    temperature: float = 1
    api_key_env: str = "OPENAI_API_KEY"

    def get_api_key(self) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"OpenAI API key not found in env var {self.api_key_env}")
        return api_key


@dataclass
class GitHubConfig:
    token_env: str = "GITHUB_TOKEN"

    def get_token(self) -> str:
        token = os.getenv(self.token_env)
        if not token:
            raise RuntimeError(f"GitHub token not found in env var {self.token_env}")
        return token


@dataclass
class ShortcutConfig:
    token_env: str = "SHORTCUT_TOKEN"

    def get_token(self) -> Optional[str]:
        # Shortcut integration is optional; return None if not configured
        return os.getenv(self.token_env)


@dataclass
class RenderConfig:
    outfile: str = "RELEASE_NOTES.md"
    sort_by_area: bool = True
    include_contributors: bool = True


@dataclass
class ReleaseConfig:
    title: str = "Release"
    since_ref: Optional[str] = None
    until_ref: Optional[str] = None


@dataclass
class Config:
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    repos: List[RepoSpec] = field(default_factory=list)
    llm: LLMConfig = field(default_factory=LLMConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    shortcut: ShortcutConfig = field(default_factory=ShortcutConfig)
    render: RenderConfig = field(default_factory=RenderConfig)


def load_config(path: Optional[str]) -> Config:
    if not path:
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    release = ReleaseConfig(**(data.get("release") or {}))

    repos_data = data.get("repos") or []
    repos = [RepoSpec(**r) for r in repos_data]

    llm = LLMConfig(**(data.get("llm") or {}))
    github = GitHubConfig(**(data.get("github") or {}))
    shortcut = ShortcutConfig(**(data.get("shortcut") or {}))
    render = RenderConfig(**(data.get("render") or {}))

    return Config(release=release, repos=repos, llm=llm, github=github, shortcut=shortcut, render=render)
