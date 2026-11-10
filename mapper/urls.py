from django.urls import path
from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _

from . import views

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html", extra_context={"title": _("Home")}), name="home"),
    path("about/", TemplateView.as_view(template_name="about.html", extra_context={"title": _("About")}), name="about"),

    # Ontology CRUD
    path("list/", views.list_ontologies, name="list_ontologies"),
    path("new/", views.create_ontology, name="create_ontology"),
    path("<int:ontology_id>/", views.detail_ontology, name="detail_ontology"),
    path("<int:ontology_id>/edit/", views.update_ontology, name="update_ontology"),
    path("<int:ontology_id>/delete/", views.delete_ontology, name="delete_ontology"),

    # Field CRUD
    path("<int:ontology_id>/import/", views.import_fields, name="import_fields"),
    path("<int:ontology_id>/review/", views.review_next_field, name="review"),
    path("<int:ontology_id>/field/<int:field_id>/review/", views.review_field, name="review_field"),
    path("<int:ontology_id>/field/<int:field_id>/decide/", views.decide, name="decide"),
    path("<int:ontology_id>/field/<int:field_id>/ask-ai/", views.ask_ai, name="ask_ai"),
    path("ai-relay/", views.ai_relay, name="ai_relay"),
    path("<int:ontology_id>/reset/", views.reset_ontology, name="reset_ontology"),
    path("<int:ontology_id>/export/", views.export, name="export"),
]