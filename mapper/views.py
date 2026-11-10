import csv
import io
import json
import requests
import ipaddress
import socket
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_variables

from .forms import OntologyForm, ImportFieldsForm
from .models import MappingDecision, Ontology, OntologyField
from .services import review as review_service
from .services.export_frictionless import build_frictionless_package


# ======================================================================================================================
# ONTOLOGY
# ======================================================================================================================
# CREATE
@login_required
@require_http_methods(["GET", "POST"])
def create_ontology(request):
    """
    Create a new ontology map
    """
    form = OntologyForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ontology = form.save(commit=False)
        ontology.created_by = request.user
        ontology.updated_by = request.user
        ontology.save()

        messages.success(request, _("Ontology created!"))
        return redirect(reverse("detail_ontology", kwargs={"ontology_id": ontology.id}))

    context = {"form": form}

    return render(request, "ontology_form.html", context)


# RETRIEVE
@require_http_methods(["GET"])
def list_ontologies(request):
    """
    List ontologies the request user has access to
    """

    public = Q(visibility=Ontology.Visibility.PUBLIC)

    if request.user.is_authenticated:
        username = request.user.get_username()
        restricted_ids = [o.id for o in Ontology.objects.filter(visibility=Ontology.Visibility.RESTRICTED) if username in (o.authorized_usernames or [])]
        ontologies_created_by_user = Ontology.objects.filter(created_by=request.user)
        ontologies_allowed = Ontology.objects.filter(public | Q(id__in=restricted_ids)).exclude(created_by=request.user)
    else:
        ontologies_created_by_user = Ontology.objects.none()
        ontologies_allowed = Ontology.objects.none()

    context = {"owned_by_user": ontologies_created_by_user, "ontologies_allowed": ontologies_allowed}

    return render(request, "list_ontologies.html", context)


@login_required
@require_http_methods(["GET"])
def detail_ontology(request, ontology_id):
    """
    Retrieve a specific ontology and its fields from the database
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_permission(ontology, request.user)

    fields = ontology.fields.select_related("decision", "decision__chosen_property", "decision__suggested_property").order_by("id")

    context = {"ontology": ontology, "fields": fields, "can_edit": ontology.can_edit(request.user)}

    return render(request, "detail_ontology.html", context)


# UPDATE
@login_required
@require_http_methods(["GET", "POST"])
def update_ontology(request, ontology_id):
    """
    Edit an ontology the user can edit
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    form = OntologyForm(request.POST or None, instance=ontology)
    if request.method == "POST" and form.is_valid():
        ontology = form.save(commit=False)
        ontology.updated_by = request.user
        ontology.save()
        messages.success(request, _("Ontology updated!"))
        return redirect(reverse("list_ontologies"))

    context = {"form": form, "ontology": ontology}

    return render(request, "ontology_form.html", context)


# DELETE
@login_required
@require_http_methods(["POST"])
def delete_ontology(request, ontology_id):
    """
    Delete an ontology the user can edit, together with its fields and decisions.
    Confirmation happens in the browser, before the form is sent.
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    ontology.delete()
    messages.success(request, _("Ontology deleted!"))
    return redirect(reverse("list_ontologies"))


# ======================================================================================================================
# ONTOLOGY FIELDS
# ======================================================================================================================
# IMPORT FIELDS
@login_required
@require_http_methods(["GET", "POST"])
def import_fields(request, ontology_id):
    ontology = get_object_or_404(Ontology, pk=ontology_id, created_by=request.user)
    form = ImportFieldsForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            read_fields_csv(ontology, form.cleaned_data["file"], request.user)
        except ValueError as error:
            form.add_error("file", str(error))
        else:
            return redirect("detail_ontology", ontology_id=ontology.id)
    return render(request, "import_fields.html", {"form": form, "ontology": ontology})


@login_required
@require_http_methods(["GET"])
def review_next_field(request, ontology_id):
    """
    Reviews one field at a time.
    Sends the user to the detail_ontology when none is left.
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    field = review_service.next_pending_field(ontology, after_id=request.GET.get("after"))
    if field is None:
        return redirect(reverse("detail_ontology", kwargs={"ontology_id": ontology.id}))

    context = review_service.build_review_context(ontology, field)

    return render(request, "review.html", context)


@login_required
@require_http_methods(["GET"])
def review_field(request, ontology_id, field_id):
    """Reviews one specific field, even if already decided."""

    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    field = get_object_or_404(OntologyField, pk=field_id, ontology=ontology)

    context = review_service.build_review_context(ontology, field)

    return render(request, "review.html", context)


@login_required
@require_http_methods(["POST"])
def decide(request, ontology_id, field_id):
    """
    It registers the user's decision on a field
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    field = get_object_or_404(OntologyField, pk=field_id, ontology_id=ontology_id)
    review_service.record_decision(field, request.POST, request.user)

    return redirect(reverse("review", kwargs={"ontology_id":ontology_id}))


@login_required
@require_http_methods(["POST"])
def ask_ai(request, ontology_id, field_id):
    """
    Stores the AI suggestion computed in the reviewer's browser
    """
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_edit_permission(ontology, request.user)

    field = get_object_or_404(OntologyField, pk=field_id, ontology_id=ontology_id)
    if not review_service.record_ai_suggestion(field, request.POST):
        messages.error(request, _("The AI answer could not be saved."))

    return redirect(reverse("review_field", kwargs={"ontology_id": ontology_id, "field_id": field_id}))


def is_public_host(hostname):
    """True only if every address the name resolves to is on the public internet."""
    try:
        addresses = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return False
    return bool(addresses) and all(ipaddress.ip_address(info[4][0]).is_global for info in addresses)


@login_required
@require_http_methods(["POST"])
@sensitive_variables("key")
def ai_relay(request):
    """
    Forwards a chat completion to an allowed AI provider, for providers that block browser calls (CORS).
    The key comes in a header, is used once and is never stored or logged.
    """
    key = request.headers.get("X-AI-Key", "")
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()

    base = payload.get("url", "")
    body = payload.get("body")
    parsed = urlparse(base)
    if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or parsed.username or parsed.password
            or not parsed.hostname
            or not is_public_host(parsed.hostname)
            or not key
            or not isinstance(body, dict)
    ):
        return HttpResponseBadRequest()

    endpoint = base.rstrip("/").removesuffix("/chat/completions") + "/chat/completions"
    try:
        upstream = requests.post(endpoint, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60, allow_redirects=False)
    except requests.RequestException:
        return JsonResponse({"error": "unreachable"}, status=502)

    return HttpResponse(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))


@login_required
@require_http_methods(["GET"])
def export(request, ontology_id):
    """Export the ontology decisions, property proposals and QuickStatements commands mockup"""
    ontology = get_object_or_404(Ontology, pk=ontology_id)
    raise_error_if_no_permission(ontology, request.user)

    package, _warnings = build_frictionless_package(ontology_id)

    timestamp = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
    response = HttpResponse(package, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="mapping_ontology_{ontology_id}_frictionless_{timestamp}.zip"'

    return response


@login_required
@require_http_methods(["POST"])
def reset_ontology(request, ontology_id):
    """Deletes every decision (and gap proposals), putting all fields back in the queue."""
    ontology = get_object_or_404(Ontology, pk=ontology_id)

    raise_error_if_no_edit_permission(ontology, request.user)

    MappingDecision.objects.filter(ontology_field__ontology=ontology).delete()

    return redirect(reverse("detail_ontology", kwargs={"ontology_id":ontology_id}))


# ======================================================================================================================
# FUNCTIONS
# ======================================================================================================================
def raise_error_if_no_permission(ontology, user):
    if not ontology.can_view(user):
        raise Http404


def raise_error_if_no_edit_permission(ontology, user):
    if not ontology.can_edit(user):
        raise Http404


def read_fields_csv(ontology, uploaded, user):
    """Creates an OntologyField per row in the CSV file; it ignores empty names or already existent ones."""
    raw = uploaded.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    if "name" not in headers:
        raise ValueError(_("The file needs a 'name' column."))

    existing = set(OntologyField.objects.filter(ontology=ontology).values_list("name", flat=True))
    new_fields = []
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name = row.get("name")
        if not name or name in existing:
            continue
        existing.add(name)
        new_fields.append(OntologyField(
            ontology=ontology,
            name=name,
            description=row.get("description", ""),
            datatype=row.get("datatype", ""),
            sample_value=row.get("sample_value", ""),
        ))
    OntologyField.objects.bulk_create(new_fields)
    ontology.updated_by = user
    ontology.save()
    return len(new_fields)
