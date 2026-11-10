"""
CSV export compatible with QuickStatements / OpenRefine, following the
"frictionless data" approach (metadata kept alongside the tabular data;
see the Glossary in the technical plan).

Each row is: item QID, PID, value, source field.
The QID is left blank on purpose when the item doesn't exist in Wikidata
yet. Item creation is out of scope here and must be resolved before the
final export (e.g. QuickStatements CREATE for new items).
"""

import csv
import io

from mapper.models import MappingDecision
from mapper.services.validation import validate_decision

HEADER = ["qid", "property", "value", "source_field"]


def _valid_decisions(ontology_id: int):
    return MappingDecision.objects.filter(
        ontology_field__ontology_id=ontology_id,
        status=MappingDecision.STATUS_VALID,
    ).select_related("ontology_field", "chosen_property")


def _row(decision: MappingDecision) -> list[str]:
    field = decision.ontology_field
    return [
        "",  # item QID, filled in later, outside this export
        decision.chosen_property.pid,
        field.sample_value,
        field.name,
    ]


def build_quickstatements_csv(ontology_id: int) -> tuple[str, list[str]]:
    """Builds the export CSV for an ontology.

    Returns (csv_content, warnings). `warnings` lists valid decisions that
    failed structural validation and were therefore left out: the export
    never includes a row that didn't pass validation.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)

    warnings = []
    for decision in _valid_decisions(ontology_id):
        result = validate_decision(decision)
        if not result.valid:
            warnings.append(f"{decision.ontology_field.name}: {'; '.join(result.errors)}")
            continue
        writer.writerow(_row(decision))

    return buffer.getvalue(), warnings
