"""
Export as a Frictionless Data Package (https://frictionlessdata.io),
complementing the QuickStatements CSV with:
  - datapackage.json: machine-readable metadata (field schema)
  - REPORT.md: human-readable explanation of what was decided and why
  - property_proposals/*.wiki: one Wikidata property proposal draft per modeling gap
"""

import io
import json
import zipfile
from datetime import datetime, timezone

from django.utils.text import slugify
from django.utils.translation import gettext as _

from mapper.models import Ontology, PropertyProposal
from mapper.services.export_quickstatements import HEADER, build_quickstatements_csv

CSV_PATH = "mapping_quickstatements.csv"

# Free-text datatype (as typed in the review) -> datatype id used by Template:Property proposal.
PROPOSAL_DATATYPES = {
    "string": "string", "text": "string", "texto": "string",
    "item": "item", "wikibase-item": "item",
    "quantity": "quantity", "number": "quantity", "numero": "quantity", "número": "quantity",
    "date": "time", "time": "time", "data": "time",
    "url": "url",
    "external-id": "external-id", "external id": "external-id", "identifier": "external-id", "identificador": "external-id",
    "monolingualtext": "monolingualtext",
    "image": "commonsMedia", "imagem": "commonsMedia", "commonsmedia": "commonsMedia",
}


def _schema_fields():
    descriptions = {
        "qid": _("Wikidata item QID (empty when the item doesn't exist yet)"),
        "property": _("PID of the property chosen during review"),
        "value": _("Sample value taken from the institutional field"),
        "source_field": _("Name of the field in the source institutional ontology"),
    }
    return [
        {"name": column, "type": "string", "description": descriptions[column]}
        for column in HEADER
    ]


def _datapackage(ontology, created):
    return {
        "profile": "tabular-data-package",
        "name": f"mapping-{ontology.id}",
        "title": _("Ontology mapping: %(name)s") % {"name": ontology.title},
        "description": _(
            "Mapping of the fields of the institutional ontology of "
            "'%(institution)s' to Wikidata properties. Deployment mode: %(mode)s."
        ) % {
            "institution": ontology.institution,
            "mode": ontology.get_deployment_mode_display(),
        },
        "created": created,
        "resources": [
            {
                "name": "mapping-quickstatements",
                "path": CSV_PATH,
                "format": "csv",
                "mediatype": "text/csv",
                "schema": {"fields": _schema_fields()},
            }
        ],
    }


def _proposal_path(proposal):
    return f"property_proposals/{proposal.pk}-{slugify(proposal.proposed_label) or 'proposal'}.wiki"


def _decision_lines(decision):
    if decision is None:
        return ["- " + _("Status: not reviewed yet")]

    lines = ["- " + _("Status: %(status)s") % {"status": decision.get_status_display()}]
    if decision.chosen_property:
        lines.append("- " + _("Chosen property: %(pid)s (%(label)s)") % {
            "pid": decision.chosen_property.pid,
            "label": decision.chosen_property.label,
        })
    if decision.chosen_source:
        lines.append("- " + _("Choice source: %(source)s") % {
            "source": decision.get_chosen_source_display(),
        })
    if decision.ai_justification:
        lines.append("- " + _("AI justification: %(justification)s") % {
            "justification": decision.ai_justification,
        })
    if hasattr(decision, "proposal"):
        lines.append("- " + _("Gap recorded: proposal '%(label)s' (%(datatype)s), draft in %(path)s") % {
            "label": decision.proposal.proposed_label,
            "datatype": decision.proposal.proposed_datatype or "?",
            "path": _proposal_path(decision.proposal),
        })
    return lines


def _report_md(ontology, warnings, created):
    lines = [
        "# " + _("Mapping report: %(name)s") % {"name": ontology.title},
        "",
        _("Institution: %(institution)s") % {"institution": ontology.institution},
        _("Deployment mode: %(mode)s") % {"mode": ontology.get_deployment_mode_display()},
        _("Generated at: %(created)s") % {"created": created},
        "",
        "## " + _("Decisions by field"),
        "",
    ]

    fields = ontology.fields.select_related(
        "decision", "decision__chosen_property", "decision__proposal"
    ).order_by("id")

    for field in fields:
        lines.append(f"### {field.name}")
        lines.append("- " + _("Description: %(description)s") % {
            "description": field.description or _("(no description)"),
        })
        lines.extend(_decision_lines(getattr(field, "decision", None)))
        lines.append("")

    if warnings:
        lines.append("## " + _("Validation warnings (left out of the CSV)"))
        lines.append("")
        lines.extend(f"- {warning}" for warning in warnings)

    return "\n".join(lines)


def _proposal_wikitext(proposal, ontology):
    """Draft of a Wikidata property proposal page, following the official preload.

    Paste it into a new page Wikidata:Property proposal/<name>. Template and section
    markup stay in English on purpose; label and description go in the ontology's language.
    """
    field = proposal.decision.ontology_field
    language = ontology.language or "en"
    raw_type = (proposal.proposed_datatype or "").strip()
    datatype = PROPOSAL_DATATYPES.get(raw_type.lower(), raw_type)
    example = f"<!-- item --> → {field.sample_value}" if field.sample_value else ""
    english_hint = "" if language == "en" else "\n<!-- | en = add the English version here -->"

    return "\n".join([
        f"== {{{{TranslateThis | anchor = {language}",
        f"| {language} = {proposal.proposed_label}{english_hint}",
        "}} ==",
        "{{Property proposal",
        "|description\t\t= {{TranslateThis",
        f" | {language} = {field.description or '<!-- description -->'}{english_hint}",
        " }}",
        "|status = <!-- leave this empty -->",
        f"|datatype\t\t= {datatype}",
        f"|example 1\t\t= {example}",
        "|example 2\t\t= ",
        "|example 3\t\t= ",
        "|subpage\t\t= {{subst:SUBPAGENAME}}",
        "|topic = generic",
        f"|planned use            = Mapping of the metadata field '{field.name}' of {ontology.institution} ({ontology.title}) to Wikidata.",
        "|number of ids          =",
        "|expected completeness  =",
        "|formatter URL\t\t=",
        "|implied notability =",
        "|external links         =",
        "|see also               =",
        "|robot and gadget jobs\t=",
        "|applicable stated in value =",
        "|single value constraint      =",
        "|distinct values constraint   =",
        "|Wikidata project  =",
        "}}",
        "",
        "=== {{Int Motivation}} ===",
        "",
        (proposal.justification or "<!-- why no existing property fits this field -->") + " ~~~~",
        "",
        "==={{int:Talk}}===",
        "",
    ])


def _proposals(ontology):
    return PropertyProposal.objects.filter(
        decision__ontology_field__ontology=ontology
    ).select_related("decision__ontology_field").order_by("id")


def build_frictionless_package(ontology_id) -> tuple[bytes, list[str]]:
    """Builds the full Data Package (zip) and returns (content, warnings)."""
    ontology = Ontology.objects.get(pk=ontology_id)
    created = datetime.now(timezone.utc).isoformat()
    csv_content, warnings = build_quickstatements_csv(ontology_id)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(CSV_PATH, csv_content)
        zf.writestr(
            "datapackage.json",
            json.dumps(_datapackage(ontology, created), ensure_ascii=False, indent=2),
        )
        zf.writestr("REPORT.md", _report_md(ontology, warnings, created))
        for proposal in _proposals(ontology):
            zf.writestr(_proposal_path(proposal), _proposal_wikitext(proposal, ontology))

    return zip_buffer.getvalue(), warnings