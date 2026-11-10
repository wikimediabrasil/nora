from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Ontology

class UsernameListField(forms.MultipleChoiceField):
    """Accepts any username typed and saves as a list."""

    def valid_value(self, value):
        return True

    def clean(self, value):
        return [n.strip() for n in super().clean(value) if n.strip()]


class OntologyForm(forms.ModelForm):
    authorized_usernames = UsernameListField(
        required=False,
        label=_("Authorized usernames"),
        help_text=_("Usernames allowed to access this ontology"),
        widget=forms.SelectMultiple(attrs={"class": "tags"}),
    )

    class Meta:
        model = Ontology
        fields = ["title", "institution", "description", "language", "deployment_mode", "wikibase_sparql_endpoint", "wikibase_api_endpoint", "visibility", "authorized_usernames"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": _("e.g. Museu Paulista postcards collection")}),
            "institution": forms.TextInput(attrs={"placeholder": _("e.g. Museu Paulista")}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "language": forms.TextInput(attrs={"placeholder": _("Language code used to search Wikidata or Wikibase, e.g. en")}),
            "wikibase_api_endpoint": forms.URLInput(attrs={"placeholder": _("API endpoint for the federated Wikibase, if not Wikidata")}),
            "wikibase_sparql_endpoint": forms.URLInput(attrs={"placeholder": _("SPARQL endpoint for the federated Wikibase, if not Wikidata")}),
        }
        help_texts = {
            "deployment_mode": _("Map directly to Wikidata, or to your own Wikibase federated with Wikidata"),
            "visibility": _("Private: only you. Restricted: you and the authorized usernames. Public: any logged user."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        own = set(self.Meta.help_texts) | {"authorized_usernames"}
        for name, field in self.fields.items():
            if name not in own:
                field.help_text = ""

        names = list(self.instance.authorized_usernames or [])
        if self.is_bound:
            names += self.data.getlist(self.add_prefix("authorized_usernames"))
        self.fields["authorized_usernames"].choices = [(n, n) for n in dict.fromkeys(names)]
        self.initial["authorized_usernames"] = names

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("deployment_mode") == "wikibase":
            for field_name in ("wikibase_sparql_endpoint", "wikibase_api_endpoint"):
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, _("Required when the implementation mode is a federated Wikibase."))
        return cleaned_data


class ImportFieldsForm(forms.Form):
    file = forms.FileField(
        label=_("CSV file"),
        help_text=_("Columns: name, description, datatype, sample_value. Only name is required."),
    )