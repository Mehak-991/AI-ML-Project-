"""Global runtime settings managed by Super Admins.

Only keys declared in SETTING_DEFINITIONS can be stored, each with a fixed type, so the
table can never be used to smuggle in arbitrary configuration. Secrets (database URL,
JWT key, ...) are deliberately NOT runtime settings: they stay in the environment.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DataValidationError
from app.database.models.system_setting import SystemSetting
from app.database.models.user import User
from app.services import audit_service


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    type: type
    default: Any
    description: str
    max_length: int | None = None


SETTING_DEFINITIONS: dict[str, SettingDefinition] = {
    d.key: d
    for d in (
        SettingDefinition(
            "allow_self_registration",
            bool,
            True,
            "Allow anyone to create a 'user' account through the sign-up form.",
        ),
        SettingDefinition(
            "maintenance_mode",
            bool,
            False,
            "Block every data-changing request except those made by super admins.",
        ),
        SettingDefinition(
            "announcement_banner",
            str,
            "",
            "Message shown to every signed-in user (empty = hidden).",
            max_length=500,
        ),
    )
}


def _coerce(definition: SettingDefinition, value: Any) -> Any:
    # bool is a subclass of int; require exact types so "1" or 1 never become True.
    if type(value) is not definition.type:
        raise DataValidationError(
            f"Setting '{definition.key}' must be of type {definition.type.__name__}."
        )
    if isinstance(value, str):
        value = value.strip()
        if definition.max_length is not None and len(value) > definition.max_length:
            raise DataValidationError(
                f"Setting '{definition.key}' may be at most {definition.max_length} characters."
            )
    return value


def get_all(session: Session | None) -> dict[str, Any]:
    values = {key: d.default for key, d in SETTING_DEFINITIONS.items()}
    if session is None:
        return values
    for row in session.scalars(select(SystemSetting)).all():
        definition = SETTING_DEFINITIONS.get(row.key)
        if definition is not None and type(row.value) is definition.type:
            values[row.key] = row.value
    return values


def get_value(session: Session | None, key: str) -> Any:
    definition = SETTING_DEFINITIONS[key]
    if session is None:
        return definition.default
    row = session.get(SystemSetting, key)
    if row is None or type(row.value) is not definition.type:
        return definition.default
    return row.value


def update(session: Session, actor: User, changes: dict[str, Any]) -> dict[str, Any]:
    if not changes:
        raise DataValidationError("No settings to update.")
    unknown = sorted(set(changes) - set(SETTING_DEFINITIONS))
    if unknown:
        raise DataValidationError("Unknown settings.", details={"unknown": unknown})
    applied: dict[str, dict[str, Any]] = {}
    for key, raw in changes.items():
        definition = SETTING_DEFINITIONS[key]
        value = _coerce(definition, raw)
        row = session.get(SystemSetting, key)
        old = row.value if row is not None else definition.default
        if old == value:
            continue
        if row is None:
            session.add(SystemSetting(key=key, value=value, updated_by_id=actor.id))
        else:
            row.value = value
            row.updated_by_id = actor.id
        applied[key] = {"old": old, "new": value}
    if applied:
        audit_service.record(
            session,
            actor=actor,
            action="settings.update",
            category="settings",
            target_type="system_settings",
            details={"changes": applied},
        )
    session.commit()
    return get_all(session)
