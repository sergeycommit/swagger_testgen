"""
Configuration helper for the test case generator.
"""

import os
import yaml
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    """Utility wrapper around user-provided and default configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config helper.

        Args:
            config_path: Optional path to a YAML config file
        """
        # Load user config if provided
        self._config = {}
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}

        # Default values
        self.defaults = {
            "llm": {
                "base_url": "https://openrouter.ai/api/v1",  # OpenRouter by default; can be set to a local endpoint
                "model": "openai/gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 4000,
                "retry_attempts": 3,
                "retry_delay": 2,
                "max_concurrent_requests": None  # None or 0 means "no limit" for async fan-out
            },
            "generation": {
                "enable_deduplication": True,
                "validation": {
                    "min_negative_cases_per_param": None,
                    "min_total_cases_per_operation": None
                }
            },
            "filters": {
                "include_paths": [],
                "exclude_paths": [],
                "include_methods": [],
                "include_tags": []
            },
            "export": {
                "format": "csv",
                "encoding": "utf-8"
            }
        }

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-path (e.g. 'llm.model').

        Args:
            key_path: Dot-separated path
            default: Value returned when the key is missing

        Returns:
            Config value or `default`
        """
        keys = key_path.split('.')
        
        # First check the user-provided config
        value = self._config
        found_in_user_config = True
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                found_in_user_config = False
                break
        
        # Fallback to defaults
        if not found_in_user_config:
            value = self.defaults
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
        
        return value if value is not None else default

    @property
    def llm_api_key(self) -> str:
        """LLM API key (OpenRouter or any compatible provider)."""
        # Prefer environment variable
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            # Fallback to a generic variable name
            api_key = os.getenv("LLM_API_KEY", "")
        return api_key

    @property
    def llm_base_url(self) -> str:
        """Base URL for the LLM API."""
        return self.get("llm.base_url", self.defaults["llm"]["base_url"])

    @property
    def llm_model(self) -> str:
        """LLM model identifier."""
        return self.get("llm.model", self.defaults["llm"]["model"])

    @property
    def llm_temperature(self) -> float:
        """Sampling temperature for the LLM."""
        return self.get("llm.temperature", self.defaults["llm"]["temperature"])

    @property
    def llm_max_tokens(self) -> int:
        """Maximum tokens per request."""
        return self.get("llm.max_tokens", self.defaults["llm"]["max_tokens"])

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts."""
        return self.get("llm.retry_attempts", self.defaults["llm"]["retry_attempts"])

    @property
    def retry_delay(self) -> int:
        """Delay between retries (seconds)."""
        return self.get("llm.retry_delay", self.defaults["llm"]["retry_delay"])

    @property
    def max_concurrent_requests(self) -> Optional[int]:
        """Max number of concurrent requests; None/0 = unlimited."""
        value = self.get("llm.max_concurrent_requests", self.defaults["llm"]["max_concurrent_requests"])
        return None if value is None or value == 0 else value

    @property
    def enable_deduplication(self) -> bool:
        """Return True when deduplication is enabled."""
        return self.get("generation.enable_deduplication", self.defaults["generation"]["enable_deduplication"])

    def should_process_path(self, path: str) -> bool:
        """Return True when the API path passes include/exclude filters."""
        include_paths = self.get("filters.include_paths", [])
        exclude_paths = self.get("filters.exclude_paths", [])
        
        if include_paths and not any(path.startswith(p) for p in include_paths):
            return False
        
        if exclude_paths and any(path.startswith(p) for p in exclude_paths):
            return False
        
        return True

    def should_process_method(self, method: str) -> bool:
        """Return True when the HTTP method passes filters."""
        include_methods = self.get("filters.include_methods", [])
        if include_methods:
            return method.upper() in [m.upper() for m in include_methods]
        return True

    def should_process_tag(self, tags: list) -> bool:
        """Return True when at least one tag matches the filter (if any)."""
        include_tags = self.get("filters.include_tags", [])
        if include_tags:
            return any(tag in include_tags for tag in tags)
        return True

