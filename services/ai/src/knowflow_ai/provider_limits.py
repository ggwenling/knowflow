"""Immutable deployment policy for provider deadlines and isolation."""
from dataclasses import dataclass
import math
import os
import re

from .config import ConfigurationError


@dataclass(frozen=True)
class TimeoutProfile:
    connect: float
    first: float
    total: float


# Attribute, exact environment name, default, minimum, maximum, integer.
LIMIT_FIELDS = (
    ('connect_max', 'KNOWFLOW_LLM_CONNECT_TIMEOUT_MAX_SECONDS', 5, .1, 10, False),
    ('first_max', 'KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_MAX_SECONDS', 20, .1, 25, False),
    ('total_max', 'KNOWFLOW_LLM_TOTAL_TIMEOUT_MAX_SECONDS', 25, 1, 25, False),
    ('connect', 'KNOWFLOW_LLM_CONNECT_TIMEOUT_SECONDS', 3, .1, 10, False),
    ('first', 'KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_SECONDS', 10, .1, 25, False),
    ('total', 'KNOWFLOW_LLM_TOTAL_TIMEOUT_SECONDS', 25, 1, 25, False),
    ('custom_connect', 'KNOWFLOW_CUSTOM_LLM_CONNECT_TIMEOUT_SECONDS', 3, .1, 10, False),
    ('custom_first', 'KNOWFLOW_CUSTOM_LLM_FIRST_TOKEN_TIMEOUT_SECONDS', 10, .1, 25, False),
    ('custom_total', 'KNOWFLOW_CUSTOM_LLM_TOTAL_TIMEOUT_SECONDS', 25, 1, 25, False),
    ('custom_requests', 'KNOWFLOW_CUSTOM_LLM_MAX_CONCURRENT_REQUESTS', 2, 1, 32, True),
    ('per_user', 'KNOWFLOW_LLM_MAX_CONCURRENT_PER_USER', 2, 1, 16, True),
    ('per_model', 'KNOWFLOW_CUSTOM_LLM_MAX_CONCURRENT_PER_MODEL', 1, 1, 8, True),
    ('failure_threshold', 'KNOWFLOW_LLM_BREAKER_FAILURE_THRESHOLD', 3, 1, 20, True),
    ('cooldown', 'KNOWFLOW_LLM_BREAKER_COOLDOWN_SECONDS', 30, 1, 300, False),
)


@dataclass(frozen=True)
class ProviderLimits:
    connect_max: float = 5
    first_max: float = 20
    total_max: float = 25
    connect: float = 3
    first: float = 10
    total: float = 25
    custom_connect: float = 3
    custom_first: float = 10
    custom_total: float = 25
    custom_requests: int = 2
    per_user: int = 2
    per_model: int = 1
    failure_threshold: int = 3
    cooldown: float = 30

    def __post_init__(self):
        for attr, _, _, low, high, integer in LIMIT_FIELDS:
            value = getattr(self, attr)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or (integer and type(value) is not int)
                    or not math.isfinite(value) or not low <= value <= high):
                raise ConfigurationError('LLM_LIMITS_CONFIGURATION_INVALID')
        if not self.connect_max <= self.first_max <= self.total_max:
            raise ConfigurationError('LLM_LIMITS_CONFIGURATION_INVALID')

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        values = {}
        try:
            for attr, name, default, _, _, integer in LIMIT_FIELDS:
                raw = env.get(name, default)
                if isinstance(raw, bool) or (integer and not re.fullmatch(r'[+-]?\d+', str(raw))):
                    raise ValueError
                values[attr] = int(raw) if integer else float(raw)
        except (ValueError, TypeError, OverflowError):
            raise ConfigurationError('LLM_LIMITS_CONFIGURATION_INVALID') from None
        return cls(**values)

    def validate_isolation(self, *, custom_enabled, question_total):
        if custom_enabled and question_total < 2:
            raise ConfigurationError('LLM_ISOLATION_CONFIGURATION_INVALID')

    def timeout_profile(self, custom=False, probe=False):
        total = min(self.custom_total if custom else self.total, self.total_max, 5 if probe else 25)
        first = min(self.custom_first if custom else self.first, self.first_max, total)
        connect = min(self.custom_connect if custom else self.connect, self.connect_max, first)
        return TimeoutProfile(connect, first, total)
