from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ======================================================================================================================
# INSTITUTIONAL
# ======================================================================================================================
class Ontology(models.Model):
    """An institutional ontology to be mapped to Wikidata ontology."""

    class DeploymentMode(models.TextChoices):
        WIKIDATA = "wikidata", _("Wikidata")
        WIKIBASE = "wikibase", _("federated Wikibase")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Private")
        RESTRICTED = "restricted", _("Restricted")

    title = models.CharField(_("Title"), max_length=255, help_text=_("Ontology title"))
    institution = models.CharField(_("Institution"), max_length=255, help_text=_("Ontology institution"))
    description = models.TextField(_("Description"), max_length=510, help_text=_("Ontology description"), blank=True)
    language = models.CharField(_("Language"), max_length=32, help_text=_("Language code used to search Wikidata or Wikibase, e.g. pt, en, es"), default="en")
    deployment_mode = models.CharField(_("Implementation mode"), max_length=32, choices=DeploymentMode, default=DeploymentMode.WIKIDATA)
    wikibase_api_endpoint = models.URLField(_("Wikibase API endpoint"), help_text=_("e.g. https://my-wikibase.wikibase.cloud/w/api.php"), blank=True)
    wikibase_sparql_endpoint = models.URLField(_("Wikibase SPARQL endpoint"), help_text=_("SPARQL endpoint for the federated Wikibase, if not Wikidata"), blank=True)
    visibility = models.CharField(_("Visibility"), max_length=32, choices=Visibility, default=Visibility.PRIVATE)
    authorized_usernames = models.JSONField(_("Authorized usernames"), default=list, blank=True, help_text=_("Usernames allowed to access this ontology"))

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_ontologies", verbose_name=_("Created by"))
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_ontologies", verbose_name=_("Updated by"))

    class Meta:
        unique_together = ("title", "institution")
        verbose_name = _("Ontology")
        verbose_name_plural = _("Ontologies")

    @property
    def api_url(self):
        if self.deployment_mode == self.DeploymentMode.WIKIBASE and self.wikibase_api_endpoint:
            return self.wikibase_api_endpoint
        return settings.WIKIDATA_API_ENDPOINT

    def __str__(self):
        return f"{self.title} ({self.institution})"

    def can_view(self, user):
        if not user.is_authenticated:
            return False

        if user.is_superuser or self.created_by_id == user.pk:
            return True

        if self.visibility == self.Visibility.PUBLIC:
            return True

        if self.visibility == self.Visibility.RESTRICTED:
            return user.get_username() in self.authorized_usernames

        return False

    def can_edit(self, user):
        return user.is_superuser or self.created_by_id == user.id


class OntologyField(models.Model):
    """A metadata field of the institutional ontology to be mapped."""

    ontology = models.ForeignKey( Ontology, on_delete=models.CASCADE, related_name="fields", verbose_name=_("Ontology"), help_text=_("Ontology to be mapped"))
    name = models.CharField(_("Field name"), max_length=255, help_text=_("Ontology field name"))
    description = models.TextField(_("Field description"), max_length=500, help_text=_("Ontology field description"), blank=True)
    sample_value = models.CharField(_("Field example value"), max_length=500, help_text=_("Ontology field example"), blank=True)
    datatype = models.CharField(_("Field datatype"), max_length=255, help_text=_("Ontology field datatype"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("ontology", "name")
        verbose_name = _("Ontology field")
        verbose_name_plural = _("Ontology fields")

    def __str__(self):
        return f"{self.ontology.title} :: {self.name}"


# ======================================================================================================================
# WIKIDATA OR WIKIBASE
# ======================================================================================================================
class WikidataProperty(models.Model):
    """
    Local cache of a Wikidata or federated Wikibase property.
    """

    pid = models.CharField(_("PID"), max_length=25, help_text=_("Wikidata property ID"))
    api_url = models.URLField(_("API endpoint"), default=settings.WIKIDATA_API_ENDPOINT, help_text=_("Wikibase the property belongs to"))
    label = models.CharField(_("Label"), max_length=255, help_text=_("Wikidata property name"))
    description = models.TextField(_("Description"), max_length=500, help_text=_("Wikidata property value"), blank=True)
    datatype = models.CharField(_("Datatype"), max_length=255, help_text=_("Wikidata property type"))
    constraints = models.JSONField(_("Constraints"), default=dict, help_text=_("Wikidata property constraints"), blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Wikidata property")
        verbose_name_plural = _("Wikidata properties")
        unique_together = ("api_url", "pid")

    def __str__(self):
        return f"{self.pid} — {self.label}"


# ======================================================================================================================
# DECISIONS
# ======================================================================================================================
class MappingDecision(models.Model):
    """Human decision for an ontology field."""

    STATUS_PENDING = "pending"
    STATUS_VALID = "valid"
    STATUS_INVALID = "invalid"
    STATUS_AMBIGUOUS = "ambiguous"
    STATUS_MANUAL = "manual_search"
    STATUS_GAP = "gap"

    SOURCE_WIKIDATA_SEARCH = "wikidata_search"
    SOURCE_WIKIDATA_MCP = "wikidata_mcp"
    SOURCE_EXTERNAL_AI = "external_ai"
    SOURCE_MANUAL = "manual"
    SOURCE_CONSENSUS = "consensus"

    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_VALID, _("Valid")),
        (STATUS_INVALID, _("No equivalent")),
        (STATUS_AMBIGUOUS, _("Ambiguous")),
        (STATUS_MANUAL, _("Manual search")),
        (STATUS_GAP, _("Gap")),
    ]

    SOURCE_CHOICES = [
        (SOURCE_WIKIDATA_SEARCH, _("Wikidata search")),
        (SOURCE_WIKIDATA_MCP, _("Wikidata MCP")),
        (SOURCE_CONSENSUS, _("Consensus")),
        (SOURCE_EXTERNAL_AI, _("External AI")),
        (SOURCE_MANUAL, _("Manual search")),
    ]

    ontology_field = models.OneToOneField(OntologyField, on_delete=models.CASCADE, related_name="decision", help_text=_("Ontology field"))
    status = models.CharField(_("Status"), max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)

    suggested_property = models.ForeignKey(WikidataProperty, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggested_for", verbose_name=_("Suggested property"))
    ai_confidence = models.FloatField(_("AI confidence score"), default=0, help_text=_("AI confidence score"), blank=True, null=True)
    ai_justification = models.TextField(_("AI justification"), default="", help_text=_("AI justification"), blank=True)

    chosen_property = models.ForeignKey(WikidataProperty, on_delete=models.SET_NULL, null=True, blank=True, related_name="chosen_for", verbose_name=_("Property mapped"))
    chosen_source = models.CharField(_("Chosen source"), max_length=32, choices=SOURCE_CHOICES, default="", help_text=_("Chosen source"), blank=True)

    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Mapping decision")
        verbose_name_plural = _("Mapping decisions")

    def __str__(self):
        return f"{self.ontology_field} -> {self.get_status_display()}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if not is_new:
            MappingDecisionHistory.objects.create(
                decision=self,
                status=self.status,
                chosen_property=self.chosen_property,
                reviewed_by=self.reviewed_by)


class MappingDecisionHistory(models.Model):
    """Versioned history of a mapping decision."""

    decision = models.ForeignKey(MappingDecision, on_delete=models.CASCADE, related_name="history", verbose_name=_("Decision"), help_text=_("Decision that was made"))
    status = models.CharField(max_length=32)
    chosen_property = models.ForeignKey(WikidataProperty, on_delete=models.SET_NULL, null=True, blank=True, related_name="chosen_in_history", verbose_name=_("Chosen property"), help_text=_("Chosen property"))
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Mapping decision history")
        verbose_name_plural = _("Mapping decision histories")
        ordering = ["-recorded_at"]


class PropertyProposal(models.Model):
    """Proposal draft for a Wikidata property.

    It is generated automatically when a field is marked as 'gap'"""

    decision = models.OneToOneField(MappingDecision, on_delete=models.CASCADE, related_name="proposal")
    proposed_label = models.CharField(_("Proposed label"), max_length=255, help_text=_("Proposed label for this property"))
    proposed_datatype = models.CharField(_("Proposed datatype"), max_length=32, help_text=_("Proposed datatype for this property"))
    justification = models.TextField(_("Justification"), default="", help_text=_("Justification for this property"), blank=True)
    submitted_upstream = models.BooleanField(_("Submitted upstream"), default=False, help_text=_("Submitted upstream for this property"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Property proposal")
        verbose_name_plural = _("Property proposals")

    def __str__(self):
        return _("Proposal: %(proposed_label)s") % {"proposed_label": self.proposed_label}
