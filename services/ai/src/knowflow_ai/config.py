"""Environment-only configuration; errors deliberately exclude input values."""
from dataclasses import dataclass, field
import os
import re
from pathlib import Path


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    internal_secret: str = field(repr=False)
    contract_path: Path = field(default_factory=lambda: Path(__file__).resolve().parents[4] / 'contracts/schemas/protocol.schema.json')

    def __post_init__(self):
        if not (32 <= len(self.internal_secret) <= 256 and
                re.fullmatch(r'[A-Za-z0-9._~+/-]+=*', self.internal_secret, flags=re.ASCII)):
            raise ConfigurationError('INTERNAL_SECRET_INVALID')

    @classmethod
    def from_environment(cls):
        kwargs = {'internal_secret': os.environ.get('KNOWFLOW_INTERNAL_SHARED_SECRET', '')}
        if path := os.environ.get('KNOWFLOW_CONTRACT_PATH'):
            kwargs['contract_path'] = Path(path)
        return cls(**kwargs)
