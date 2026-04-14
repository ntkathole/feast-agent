"""Agent configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langchain_core.language_models import BaseChatModel


@dataclass
class AgentConfig:
    """Configuration for the Feast Agent.

    All values fall back to environment variables, then to sensible defaults.

    Remote connectivity
    -------------------
    To connect to a remote Feast deployment with RBAC, set:
      - ``auth_type``  — "oidc" or "kubernetes" (or "no_auth")
      - For OIDC: set ``auth_discovery_url``, ``auth_client_id``, and
        either ``auth_token`` / ``FEAST_OIDC_TOKEN`` env-var or
        ``auth_client_secret`` for client-credentials flow.
      - For Kubernetes: runs in-cluster by default (reads SA token).

    These map directly to the ``auth:`` block in ``feature_store.yaml``.
    When *both* env vars and an explicit ``feature_store.yaml`` exist,
    env-var overrides win so operators can inject tokens at runtime.
    """

    # --- Feast repo / YAML -------------------------------------------------
    repo_path: str = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_REPO_PATH", ".")
    )
    feature_store_yaml: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_FEATURE_STORE_YAML")
    )

    # --- LLM ---------------------------------------------------------------
    llm_provider: str = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_LLM_PROVIDER", "openai")
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_LLM_MODEL", "gpt-4o")
    )
    temperature: float = 0.0

    # --- Auth / RBAC -------------------------------------------------------
    auth_type: str = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_AUTH_TYPE", "no_auth")
    )
    auth_discovery_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_AUTH_DISCOVERY_URL")
    )
    auth_client_id: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_AUTH_CLIENT_ID")
    )
    auth_client_secret: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_AUTH_CLIENT_SECRET")
    )
    auth_token: Optional[str] = field(
        default_factory=lambda: os.environ.get(
            "FEAST_AGENT_AUTH_TOKEN",
            os.environ.get("FEAST_OIDC_TOKEN"),
        )
    )

    # --- Remote registry ---------------------------------------------------
    remote_registry_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_REMOTE_REGISTRY_URL")
    )
    remote_registry_tls: bool = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_REMOTE_REGISTRY_TLS", "").lower()
        in ("1", "true", "yes")
    )
    remote_registry_cert: Optional[str] = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_REMOTE_REGISTRY_CERT")
    )

    # -----------------------------------------------------------------------

    @property
    def resolved_repo_path(self) -> Path:
        return Path(self.repo_path).expanduser().resolve()

    @property
    def is_remote(self) -> bool:
        return self.remote_registry_url is not None

    # --- Ollama --------------------------------------------------------------
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get("FEAST_AGENT_OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_num_ctx: int = field(
        default_factory=lambda: int(os.environ.get("FEAST_AGENT_OLLAMA_NUM_CTX", "16384"))
    )

    def build_chat_model(self) -> BaseChatModel:
        """Construct the LangChain chat model for the configured provider."""
        provider = self.llm_provider.lower()
        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError:
                raise ImportError(
                    "Install the OpenAI integration: pip install 'feast-agent[openai]'"
                )
            return ChatOpenAI(model=self.llm_model, temperature=self.temperature)

        if provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError:
                raise ImportError(
                    "Install the Anthropic integration: pip install 'feast-agent[anthropic]'"
                )
            return ChatAnthropic(model=self.llm_model, temperature=self.temperature)

        if provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                raise ImportError(
                    "Install the Ollama integration: pip install 'feast-agent[ollama]'"
                )
            return ChatOllama(
                model=self.llm_model,
                base_url=self.ollama_base_url,
                temperature=self.temperature,
                num_ctx=self.ollama_num_ctx,
            )

        raise ValueError(
            f"Unsupported LLM provider '{provider}'. Use 'openai', 'anthropic', or 'ollama'."
        )

    # -- Auth helpers -------------------------------------------------------

    def _build_auth_dict(self) -> dict:
        """Build the ``auth:`` config dict for ``RepoConfig``."""
        auth: dict = {"type": self.auth_type}

        if self.auth_type == "oidc":
            if self.auth_discovery_url:
                auth["auth_discovery_url"] = self.auth_discovery_url
            if self.auth_client_id:
                auth["client_id"] = self.auth_client_id
            if self.auth_client_secret:
                auth["client_secret"] = self.auth_client_secret
            if self.auth_token:
                auth["token"] = self.auth_token

        elif self.auth_type == "kubernetes":
            token = self.auth_token or os.environ.get("LOCAL_K8S_TOKEN")
            if token:
                auth["user_token"] = token

        return auth

    def _build_registry_dict(self) -> dict | str:
        """Build the ``registry:`` config dict for ``RepoConfig``.

        When ``remote_registry_url`` is set, produces a remote-gRPC registry
        config; otherwise returns the default file-backed path.
        """
        if not self.remote_registry_url:
            return str(self.resolved_repo_path / "data" / "registry.db")

        reg: dict = {
            "registry_type": "remote",
            "path": self.remote_registry_url,
        }
        if self.remote_registry_tls:
            reg["is_tls"] = True
        if self.remote_registry_cert:
            reg["cert"] = self.remote_registry_cert
        return reg

    # -- FeatureStore builder -----------------------------------------------

    def build_feature_store(self):
        """Construct a Feast FeatureStore.

        If a ``feature_store.yaml`` file is supplied, it is used directly and
        the agent respects whatever ``auth`` and ``registry`` blocks it
        contains.  Environment-variable overrides (``FEAST_OIDC_TOKEN``, etc.)
        are still picked up by the Feast SDK automatically.

        When **no** YAML is provided *and* a remote registry URL is configured,
        the agent builds a ``RepoConfig`` programmatically so you can connect
        to a remote Feast deployment without any file on disk.
        """
        from feast import FeatureStore

        if self.feature_store_yaml:
            return FeatureStore(
                repo_path=str(self.resolved_repo_path),
                fs_yaml_file=self.feature_store_yaml,
            )

        if self.remote_registry_url:
            from feast import RepoConfig

            config = RepoConfig(
                project=os.environ.get("FEAST_AGENT_PROJECT", "default"),
                provider="local",
                registry=self._build_registry_dict(),
                auth=self._build_auth_dict(),
                entity_key_serialization_version=3,
            )
            return FeatureStore(config=config)

        return FeatureStore(repo_path=str(self.resolved_repo_path))
