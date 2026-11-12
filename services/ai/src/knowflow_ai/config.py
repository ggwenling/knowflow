"""Environment-only configuration; errors deliberately exclude input values."""
from dataclasses import dataclass, field
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    internal_secret: str = field(repr=False)
    contract_path: Path = field(default_factory=lambda: Path(__file__).resolve().parents[4] / 'contracts/schemas/protocol.schema.json')
    java_base_url: str = 'http://127.0.0.1:8080'
    runtime_profile_id: str = 'runtime-default'
    ai_database_url: str = field(default='', repr=False)
    max_concurrent_questions: int = 4

    def __post_init__(self):
        if not (32 <= len(self.internal_secret) <= 256 and
                re.fullmatch(r'[A-Za-z0-9._~+/-]+=*', self.internal_secret, flags=re.ASCII)):
            raise ConfigurationError('INTERNAL_SECRET_INVALID')
        try:
            parsed = urlsplit(self.java_base_url)
            port = parsed.port
        except (TypeError, ValueError):
            raise ConfigurationError('JAVA_BASE_URL_INVALID') from None
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path not in ('', '/')
                or (port is not None and not 1 <= port <= 65535)):
            raise ConfigurationError('JAVA_BASE_URL_INVALID')
        if (type(self.max_concurrent_questions) is not int
                or not 1 <= self.max_concurrent_questions <= 32):
            raise ConfigurationError('QUESTION_CONCURRENCY_INVALID')

    def provider_limits(self, environ=None):
        # Import locally: provider policy uses the same safe configuration error.
        from .provider_limits import ProviderLimits
        env = os.environ if environ is None else environ
        limits = ProviderLimits.from_environment(env)
        limits.validate_isolation(custom_enabled=str(env.get('KNOWFLOW_CUSTOM_LLM_ENABLED', '')).lower() == 'true',
                                  question_total=self.max_concurrent_questions)
        return limits

    @classmethod
    def from_environment(cls):
        kwargs = {'internal_secret': os.environ.get('KNOWFLOW_INTERNAL_SHARED_SECRET', '')}
        if path := os.environ.get('KNOWFLOW_CONTRACT_PATH'):
            kwargs['contract_path'] = Path(path)
        kwargs['java_base_url'] = os.environ.get('KNOWFLOW_JAVA_BASE_URL', 'http://127.0.0.1:8080')
        kwargs['runtime_profile_id'] = os.environ.get('KNOWFLOW_RUNTIME_PROFILE_ID', 'runtime-default')
        kwargs['ai_database_url'] = os.environ.get('KNOWFLOW_AI_DATABASE_URL', '')
        try:
            kwargs['max_concurrent_questions'] = int(os.environ.get(
                'KNOWFLOW_QUESTION_MAX_CONCURRENT', '4'))
        except ValueError:
            raise ConfigurationError('QUESTION_CONCURRENCY_INVALID') from None
        return cls(**kwargs)
