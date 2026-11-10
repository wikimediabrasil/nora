import re
import requests
from django.conf import settings
from django.utils.translation import get_language, gettext as _

from mapper.models import MappingDecision, Ontology, OntologyField, PropertyProposal

from . import wikidata_api, wikidata_mcp

DONE_STATUSES = [
    MappingDecision.STATUS_VALID,
    MappingDecision.STATUS_INVALID,
    MappingDecision.STATUS_GAP,
]

VALID_SOURCES = dict(MappingDecision.SOURCE_CHOICES)


def next_pending_field(ontology: Ontology, after_id=None):
    """Next field still waiting for a user decision.

    With `after_id`, it looks past that field first (used by "Skip") and puts it
    back to the queue if there's nothing left to decide.
    """
    queryset = (
        OntologyField.objects.filter(ontology=ontology)
        .exclude(decision__status__in=DONE_STATUSES)
        .order_by("id")
    )
    if after_id:
        next_field = queryset.filter(id__gt=after_id).first()
        if next_field is not None:
            return next_field
    return queryset.first()


def get_progress(ontology: Ontology) -> tuple[int, int, int]:
    """Returns the number of decisions done, the total number of fields and the completion percentage"""
    fields = OntologyField.objects.filter(ontology=ontology)
    total = fields.count()
    done = fields.filter(decision__status__in=DONE_STATUSES).count()
    pct = round(done / total * 100) if total else 0
    return done, total, pct


def merge_candidates(search_candidates, mcp_candidates) -> list[dict]:
    """One list of {pid, label, description, score, source}, consensus first."""
    merged = {}
    for candidate in search_candidates:
        merged[candidate["pid"]] = {
            "pid": candidate["pid"],
            "label": candidate["label"],
            "description": candidate.get("description", ""),
            "score": candidate.get("score"),
            "source": MappingDecision.SOURCE_WIKIDATA_SEARCH,
        }
    for candidate in mcp_candidates:
        if candidate["pid"] in merged:
            existing = merged[candidate["pid"]]
            existing["source"] = MappingDecision.SOURCE_CONSENSUS
            existing["description"] = existing["description"] or candidate.get("description", "")
            if existing["score"] is None:
                existing["score"] = candidate.get("score")
        else:
            merged[candidate["pid"]] = {
                "pid": candidate["pid"],
                "label": candidate["label"],
                "description": candidate.get("description", ""),
                "score": candidate.get("score"),
                "source": MappingDecision.SOURCE_WIKIDATA_MCP,
            }
    return sorted(merged.values(), key=lambda c: c["source"] != MappingDecision.SOURCE_CONSENSUS)


def build_review_context(ontology: Ontology, field: OntologyField) -> dict:
    """Everything the review template needs for one field."""
    decision, _created = MappingDecision.objects.get_or_create(ontology_field=field)
    query = f"{field.name.replace('_', ' ')} {field.description}".strip()

    candidates, search_error = [], None
    try:
        candidates = wikidata_api.search_properties(query, ontology.language, ontology.api_url)
        if candidates and decision.suggested_property_id is None:
            decision.suggested_property = wikidata_api.store_property(
                candidates[0]["pid"], ontology.language, ontology.api_url
            )
            decision.save()
    except (requests.RequestException, KeyError):
        search_error = _("Could not reach Wikidata. Try again in a few minutes.")

    candidates_mcp, mcp_error = [], None
    if settings.USE_WD_MCP and ontology.deployment_mode == Ontology.DeploymentMode.WIKIDATA:
        try:
            candidates_mcp = wikidata_mcp.find_candidates_mcp(query, language=ontology.language)
        except Exception as exc:
            mcp_error = str(exc)

    done_count, total_fields, progress_pct = get_progress(ontology)

    return {
        "ontology": ontology,
        "field": field,
        "decision": decision,
        "merged_candidates": merge_candidates(candidates, candidates_mcp),
        "search_error": search_error,
        "mcp_error": mcp_error,
        "done_count": done_count,
        "total_fields": total_fields,
        "progress_pct": progress_pct,
    }


PID_PATTERN = re.compile(r"^P\d+$")

def record_ai_suggestion(field: OntologyField, data) -> bool:
    """Saves the AI answer computed in the reviewer's browser.

    The key never reaches the server: only the PID, confidence and justification
    arrive here, and they are validated as untrusted input.
    """
    pid = (data.get("pid") or "").strip().upper()
    if not PID_PATTERN.match(pid):
        return False
    try:
        confidence = min(max(float(data.get("confidence", 0)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = None
    justification = (data.get("justification") or "").strip()[:2000]

    ontology = field.ontology
    try:
        prop = wikidata_api.store_property(pid, ontology.language, ontology.api_url)
    except (requests.RequestException, KeyError):
        return False

    decision, _created = MappingDecision.objects.get_or_create(ontology_field=field)
    decision.suggested_property = prop
    decision.ai_confidence = confidence
    decision.ai_justification = justification
    decision.save()
    return True


def record_decision(field: OntologyField, data, user) -> bool:
    """Applies the reviewer's choice (a POST payload) to the field.

    Returns False when the status is not a valid one.
    """
    status = data.get("status")
    if status not in dict(MappingDecision.STATUS_CHOICES):
        return False

    ontology = field.ontology
    decision, _created = MappingDecision.objects.get_or_create(ontology_field=field)
    decision.status = status
    decision.reviewed_by = user
    decision.chosen_property = None
    decision.chosen_source = ""

    try:
        if status == MappingDecision.STATUS_VALID:
            pid = data.get("chosen_pid") or (
                decision.suggested_property.pid if decision.suggested_property else None
            )
            if pid:
                decision.chosen_property = wikidata_api.store_property(pid, ontology.language, ontology.api_url)
            source = data.get("source", "")
            decision.chosen_source = source if source in VALID_SOURCES else ""

        elif status == MappingDecision.STATUS_MANUAL:
            manual_pid = data.get("manual_pid", "").strip().upper()
            if manual_pid:
                decision.chosen_property = wikidata_api.store_property(manual_pid, ontology.language, ontology.api_url)
            if decision.chosen_property:
                decision.status = MappingDecision.STATUS_VALID
                decision.chosen_source = MappingDecision.SOURCE_MANUAL
    except (requests.RequestException, KeyError):
        decision.status = MappingDecision.STATUS_PENDING
        decision.chosen_property = None
        decision.chosen_source = ""

    decision.save()

    if decision.status == MappingDecision.STATUS_GAP:
        PropertyProposal.objects.update_or_create(
            decision=decision,
            defaults={
                "proposed_label": data.get("proposed_label", field.name),
                "proposed_datatype": data.get("proposed_datatype", ""),
                "justification": data.get("justification", ""),
            },
        )
    else:
        PropertyProposal.objects.filter(decision=decision).delete()

    return True