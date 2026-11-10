"""Shared builders for the tests. Nothing here touches the network."""

from django.contrib.auth.models import User

from mapper.models import MappingDecision, Ontology, OntologyField, WikidataProperty

WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def make_user(username="Owner", **extra):
    return User.objects.create_user(username=username, **extra)


def make_ontology(owner, **extra):
    data = {"title": "Postcards", "institution": "Museu Paulista", "language": "pt", "created_by": owner}
    data.update(extra)
    return Ontology.objects.create(**data)


def make_field(ontology, name="data_aquisicao", **extra):
    return OntologyField.objects.create(ontology=ontology, name=name, **extra)


def make_property(pid="P580", datatype="time", **extra):
    data = {"pid": pid, "api_url": WIKIDATA_API, "label": f"label {pid}", "datatype": datatype}
    data.update(extra)
    return WikidataProperty.objects.create(**data)


def decide(field, status, prop=None, **extra):
    decision, _ = MappingDecision.objects.get_or_create(ontology_field=field)
    decision.status = status
    decision.chosen_property = prop
    for key, value in extra.items():
        setattr(decision, key, value)
    decision.save()
    return decision
