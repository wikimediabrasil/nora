from django.contrib import admin

from .models import (
    MappingDecision,
    MappingDecisionHistory,
    Ontology,
    OntologyField,
    PropertyProposal,
    WikidataProperty,
)


@admin.register(Ontology)
class OntologyAdmin(admin.ModelAdmin):
    list_display = ("title", "institution", "deployment_mode", "created_at")
    list_filter = ("deployment_mode",)


@admin.register(OntologyField)
class OntologyFieldAdmin(admin.ModelAdmin):
    list_display = ("name", "ontology", "datatype", "created_at")
    list_filter = ("ontology",)


@admin.register(WikidataProperty)
class WikidataPropertyAdmin(admin.ModelAdmin):
    list_display = ("pid", "label", "datatype", "updated_at")
    search_fields = ("pid", "label", "description")


@admin.register(MappingDecision)
class MappingDecisionAdmin(admin.ModelAdmin):
    list_display = ("ontology_field", "status", "suggested_property", "chosen_property", "ai_confidence")
    list_filter = ("status",)


@admin.register(MappingDecisionHistory)
class MappingDecisionHistoryAdmin(admin.ModelAdmin):
    list_display = ("decision", "status", "chosen_property", "recorded_at")
    readonly_fields = [f.name for f in MappingDecisionHistory._meta.fields]


@admin.register(PropertyProposal)
class PropertyProposalAdmin(admin.ModelAdmin):
    list_display = ("proposed_label", "decision", "submitted_upstream", "created_at")
