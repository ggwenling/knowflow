from dataclasses import replace
import pytest

from knowflow_ai.config import ConfigurationError
from knowflow_ai.provider_limits import ProviderLimits, LIMIT_FIELDS, TimeoutProfile
from knowflow_ai.app import create_app
from knowflow_ai.config import Settings


def test_limits_defaults_and_validated_ranges():
    defaults = ProviderLimits.from_environment({})
    assert defaults.timeout_profile() == TimeoutProfile(3, 10, 25)
    assert defaults.timeout_profile(custom=True, probe=True) == TimeoutProfile(3, 5, 5)
    assert (defaults.custom_requests, defaults.per_user, defaults.per_model,
            defaults.failure_threshold, defaults.cooldown) == (2, 2, 1, 3, 30)
    for attr, env, default, low, high, integer in LIMIT_FIELDS:
        assert getattr(defaults, attr) == default
        for bad in (True, 'NaN', 'Infinity', '', low - .01, high + 1, 'secret-invalid'):
            with pytest.raises(ConfigurationError, match='^LLM_LIMITS_CONFIGURATION_INVALID$'):
                ProviderLimits.from_environment({env: bad})
        if integer:
            for bad in ('1.5', '2.0', 1.5):
                with pytest.raises(ConfigurationError):
                    ProviderLimits.from_environment({env: bad})
        # Max combinations must remain ordered.
        for value in (low, high):
            envs = {env: str(value)}
            if attr.endswith('_max'):
                envs.update(KNOWFLOW_LLM_CONNECT_TIMEOUT_MAX_SECONDS='.1',
                            KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_MAX_SECONDS='25',
                            KNOWFLOW_LLM_TOTAL_TIMEOUT_MAX_SECONDS='25')
                envs[env] = str(value)
                if attr == 'total_max':
                    envs['KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_MAX_SECONDS'] = str(value)
            assert getattr(ProviderLimits.from_environment(envs), attr) == value
    with pytest.raises(ConfigurationError):
        replace(defaults, connect_max=6, first_max=5)
    with pytest.raises(ConfigurationError):
        replace(defaults, first_max=25, total_max=20)


def test_custom_timeout_profile_is_capped_by_system_max():
    policy = ProviderLimits(connect_max=1, first_max=2, total_max=4,
                            custom_connect=10, custom_first=25, custom_total=25)
    assert policy.timeout_profile(custom=True) == TimeoutProfile(1, 2, 4)
    assert policy.timeout_profile() == TimeoutProfile(1, 2, 4)
    assert ProviderLimits(custom_total=1).timeout_profile(custom=True) == TimeoutProfile(1, 1, 1)


def test_custom_enabled_requires_reserved_builtin_capacity(monkeypatch):
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
    with pytest.raises(ConfigurationError, match='^LLM_ISOLATION_CONFIGURATION_INVALID$'):
        create_app(Settings('a' * 40, max_concurrent_questions=1))
    create_app(Settings('a' * 40, max_concurrent_questions=2))
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'false')
    create_app(Settings('a' * 40, max_concurrent_questions=1))
