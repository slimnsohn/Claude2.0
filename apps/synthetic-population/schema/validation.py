"""Validation logic for synthetic population profiles against the standard schema."""

from schema.standard import STANDARD_SCHEMA


class ValidationError:
    """Represents a single validation error for a profile field."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        return f"ValidationError({self.field}: {self.message})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValidationError):
            return NotImplemented
        return self.field == other.field and self.message == other.message


def validate_profile(profile: dict, partial: bool = False) -> list[ValidationError]:
    """Validate a profile dict against the standard schema.

    Args:
        profile: Dictionary of field_name -> value pairs.
        partial: If True, only validate fields that are present.
                 If False, also flag missing required fields (excludes system metadata).

    Returns:
        List of ValidationError objects. Empty list means valid.
    """
    errors = []

    for field, value in profile.items():
        if field not in STANDARD_SCHEMA:
            continue  # custom/namespaced fields pass through

        spec = STANDARD_SCHEMA[field]
        field_type = spec["type"]

        # Type checks
        if field_type == "str":
            if not isinstance(value, str):
                errors.append(ValidationError(field, f"expected str, got {type(value).__name__}"))
                continue
            # Only check allowed values if the values list is non-empty
            if spec.get("values") and value not in spec["values"]:
                errors.append(ValidationError(field, f"'{value}' not in {spec['values']}"))
        elif field_type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(ValidationError(field, f"expected int, got {type(value).__name__}"))
                continue
        elif field_type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(ValidationError(field, f"expected float, got {type(value).__name__}"))
                continue
        elif field_type == "bool":
            if not isinstance(value, bool):
                errors.append(ValidationError(field, f"expected bool, got {type(value).__name__}"))
                continue

        # Range check for numeric types
        if field_type in ("int", "float") and "range" in spec:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                lo, hi = spec["range"]
                if not (lo <= value <= hi):
                    errors.append(ValidationError(field, f"{value} not in range [{lo}, {hi}]"))

    # If not partial, check for missing required fields (skip system metadata)
    if not partial:
        from schema.standard import SYSTEM_METADATA
        system_fields = set(SYSTEM_METADATA.keys())
        for field in STANDARD_SCHEMA:
            if field not in profile and field not in system_fields:
                errors.append(ValidationError(field, "required field missing"))

    return errors
