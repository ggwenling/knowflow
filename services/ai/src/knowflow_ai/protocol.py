"""Consume A's exact schema, without publishing a second schema."""
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict
from .config import ConfigurationError

CONTRACT_VERSION = '0.2.0-draft.6'
SCHEMA_SHA256 = 'd64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1'


class InvalidMessage(ValueError):
    pass


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    contract_version: str = CONTRACT_VERSION
    request_id: str
    code: str
    message: str
    retryable: bool = False


class ContractConsumer:
    def __init__(self, path: Path):
        try:
            raw = path.read_bytes()
            if sha256(raw).hexdigest() != SCHEMA_SHA256:
                raise ConfigurationError('CONTRACT_HASH_MISMATCH')
            self.schema = json.loads(raw)
            Draft202012Validator.check_schema(self.schema)
            self.formats = FormatChecker()
            if 'date-time' not in self.formats.checkers:
                raise ConfigurationError('CONTRACT_FORMAT_CHECKER_MISSING')
        except (OSError, ValueError):
            raise ConfigurationError('CONTRACT_UNAVAILABLE') from None

    def validate(self, definition: str, payload: dict[str, Any]) -> None:
        if definition not in self.schema['$defs']:
            raise InvalidMessage('UNKNOWN_MESSAGE_TYPE')
        schema = {**self.schema, '$ref': f'#/$defs/{definition}'}
        if not Draft202012Validator(schema, format_checker=self.formats).is_valid(payload):
            raise InvalidMessage('INVALID_MESSAGE')  # never stringify provider/user input
        # Cross-field semantic checks not expressible in the candidate schema.
        if definition in ('Source', 'Locator'):
            locator = payload.get('locator', payload)
            if 'start' in locator and locator['end'] <= locator['start']:
                raise InvalidMessage('INVALID_LOCATOR_RANGE')
