"""
Wikidata / Wikibase API wrapper.

Searches properties live, in the ontology's language, on the ontology's API
endpoint (Wikidata or a federated Wikibase; see Ontology.api_url). Only the
properties chosen in a review are stored locally, in WikidataProperty.
"""

import requests

from mapper.models import WikidataProperty

HEADERS = {"User-Agent": "OntologyMapper/0.1 (https://toolforge.org; tecnologia@wmnobrasil.org)"}


def _get(api_url, **params):
    response = requests.get(api_url, params={**params, "format": "json"}, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.json()


def _entities(pids, language, api_url):
    data = _get(api_url, action="wbgetentities", ids="|".join(pids),
                languages=language, languagefallback=1,
                props="labels|descriptions|datatype").get("entities", {})
    return [{
        "pid": pid,
        "label": data[pid].get("labels", {}).get(language, {}).get("value", pid),
        "description": data[pid].get("descriptions", {}).get(language, {}).get("value", ""),
        "datatype": data[pid].get("datatype", ""),
    } for pid in pids if pid in data and "missing" not in data[pid]]


def search_properties(query, language, api_url, limit=10):
    """Live full-text search over properties; returns a list of dicts."""
    hits = _get(api_url, action="query", list="search", srnamespace=120,
                srsearch=query, srlimit=limit)["query"]["search"]
    pids = [hit["title"].split(":")[-1] for hit in hits]
    return _entities(pids, language, api_url) if pids else []


def store_property(pid, language, api_url):
    """Fetches one property live and saves it locally; None if it doesn't exist."""
    found = _entities([pid], language, api_url)
    if not found:
        return None
    prop, _ = WikidataProperty.objects.update_or_create(pid=pid, api_url=api_url, defaults=found[0])
    return prop