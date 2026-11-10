"""
Structural validation before export: datatype compatibility and property constraints.

Addresses the risk "incorrect suggestions applied without structural validation"
from the technical plan. `WikidataProperty.constraints` may hold:
  - allowed_values: closed list of accepted values
  - format_regex: regular expression the value must match
"""

import re
from dataclasses import dataclass, field

from django.utils.translation import gettext as _

from mapper.models import MappingDecision

TEXT = {"string", "monolingualtext", "external-id"}
TIME = {"time"}
QUANTITY = {"quantity"}
URL = {"url"}
MEDIA = {"commonsMedia"}
ITEM = {"wikibase-item"}

# Source datatype (free text, as imported) -> compatible Wikibase datatypes.
# Includes English names, Portuguese names and Tainacan metadata types.
COMPATIBLE_DATATYPES = {
    "string": TEXT, "text": TEXT, "textarea": TEXT, "texto": TEXT,
    "date": TIME, "time": TIME, "datetime": TIME, "data": TIME,
    "number": QUANTITY, "numeric": QUANTITY, "integer": QUANTITY, "quantity": QUANTITY, "numero": QUANTITY, "número": QUANTITY,
    "url": URL, "link": URL,
    "image": MEDIA, "imagem": MEDIA, "commonsmedia": MEDIA,
    "item": ITEM, "taxonomy": ITEM, "relationship": ITEM, "wikibase-item": ITEM,
}

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_decision(decision: MappingDecision) -> ValidationResult:
    if decision.status != MappingDecision.STATUS_VALID:
        return ValidationResult(valid=True)

    prop = decision.chosen_property
    source_field = decision.ontology_field

    if prop is None:
        return ValidationResult(valid=False, errors=[_("Decision marked as valid but no property was chosen.")])

    errors = []

    # 1. Datatype compatibility
    source_type = (source_field.datatype or "").strip().lower()
    accepted = COMPATIBLE_DATATYPES.get(source_type)
    if accepted and prop.datatype and prop.datatype not in accepted:
        errors.append(_(
            "Incompatible datatype: the source field is '%(source)s', "
            "but %(pid)s (%(label)s) expects '%(expected)s'."
        ) % {"source": source_type, "pid": prop.pid, "label": prop.label, "expected": prop.datatype})

    # 2. Constraints declared on the property
    constraints = prop.constraints or {}
    value = source_field.sample_value or ""

    allowed_values = constraints.get("allowed_values")
    if allowed_values and value and value not in allowed_values:
        errors.append(_(
            "Sample value '%(value)s' is not among the allowed values for %(pid)s."
        ) % {"value": value, "pid": prop.pid})

    pattern = constraints.get("format_regex")
    if pattern and value and not re.fullmatch(pattern, value):
        errors.append(_(
            "Sample value '%(value)s' does not match the expected format for %(pid)s."
        ) % {"value": value, "pid": prop.pid})

    return ValidationResult(valid=not errors, errors=errors)