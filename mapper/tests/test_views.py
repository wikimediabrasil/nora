import json
import socket
from unittest import mock

import requests
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from mapper import views
from mapper.models import MappingDecision, Ontology, OntologyField

from .helpers import decide, make_field, make_ontology, make_property, make_user


class BaseViewTest(TestCase):
    def setUp(self):
        self.owner = make_user("Owner")
        self.other = make_user("Other")
        self.ontology = make_ontology(self.owner)
        self.client.force_login(self.owner)

    def url(self, name, **kwargs):
        kwargs.setdefault("ontology_id", self.ontology.id)
        return reverse(name, kwargs=kwargs)


class LoginAndLanguageTests(TestCase):
    def test_protected_page_redirects_to_home_with_next(self):
        response = self.client.get(reverse("create_ontology"))
        self.assertRedirects(response, f"{reverse('home')}?next={reverse('create_ontology')}")

    def test_public_pages_render_for_anonymous_users(self):
        for name in ("home", "about", "list_ontologies"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_language_can_be_changed(self):
        response = self.client.post(reverse("set_language"), {"language": "pt-br", "next": "/about/"})
        self.assertRedirects(response, "/about/", fetch_redirect_response=False)
        self.assertEqual(self.client.cookies["django_language"].value, "pt-br")


class ListOntologiesTests(BaseViewTest):
    def test_lists_own_public_and_restricted_ontologies(self):
        public = make_ontology(self.other, title="public", visibility=Ontology.Visibility.PUBLIC)
        shared = make_ontology(self.other, title="shared", visibility=Ontology.Visibility.RESTRICTED, authorized_usernames=["Owner"])
        make_ontology(self.other, title="hidden", visibility=Ontology.Visibility.RESTRICTED, authorized_usernames=["Someone"])
        make_ontology(self.other, title="private")

        context = self.client.get(reverse("list_ontologies")).context
        self.assertEqual(list(context["owned_by_user"]), [self.ontology])
        self.assertEqual(set(context["ontologies_allowed"]), {public, shared})


class OntologyCrudTests(BaseViewTest):
    def form_data(self, **extra):
        data = {"title": "New", "institution": "Museum", "language": "pt", "deployment_mode": "wikidata", "visibility": "restricted", "authorized_usernames": ["Ana", " ", "Bia"]}
        data.update(extra)
        return data

    def test_create_form_renders(self):
        self.assertEqual(self.client.get(reverse("create_ontology")).status_code, 200)

    def test_create_sets_owner_and_cleans_usernames(self):
        response = self.client.post(reverse("create_ontology"), self.form_data())
        ontology = Ontology.objects.get(title="New")
        self.assertRedirects(response, self.url("detail_ontology", ontology_id=ontology.id))
        self.assertEqual(ontology.created_by, self.owner)
        self.assertEqual(ontology.authorized_usernames, ["Ana", "Bia"])

    def test_wikibase_mode_requires_endpoints(self):
        response = self.client.post(reverse("create_ontology"), self.form_data(deployment_mode="wikibase"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("wikibase_api_endpoint", response.context["form"].errors)
        self.assertIn("wikibase_sparql_endpoint", response.context["form"].errors)

    def test_detail_for_owner_and_404_for_others(self):
        make_field(self.ontology)
        self.assertEqual(self.client.get(self.url("detail_ontology")).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("detail_ontology")).status_code, 404)

    def test_update(self):
        self.assertEqual(self.client.get(self.url("update_ontology")).status_code, 200)
        response = self.client.post(self.url("update_ontology"), self.form_data(title="Renamed"))
        self.assertRedirects(response, reverse("list_ontologies"))
        self.ontology.refresh_from_db()
        self.assertEqual(self.ontology.title, "Renamed")

    def test_viewer_cannot_edit_public_ontology(self):
        self.ontology.visibility = Ontology.Visibility.PUBLIC
        self.ontology.save()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("detail_ontology")).status_code, 200)
        self.assertEqual(self.client.get(self.url("update_ontology")).status_code, 404)
        self.assertEqual(self.client.post(self.url("delete_ontology")).status_code, 404)

    def test_delete_only_through_post(self):
        self.assertEqual(self.client.get(self.url("delete_ontology")).status_code, 405)
        self.assertRedirects(self.client.post(self.url("delete_ontology")), reverse("list_ontologies"))
        self.assertFalse(Ontology.objects.exists())


class ImportFieldsTests(BaseViewTest):
    def upload(self, content, encoding="utf-8"):
        file = SimpleUploadedFile("fields.csv", content.encode(encoding), content_type="text/csv")
        return self.client.post(self.url("import_fields"), {"file": file})

    def test_form_renders(self):
        self.assertEqual(self.client.get(self.url("import_fields")).status_code, 200)

    def test_imports_rows_and_skips_empty_and_existing_names(self):
        make_field(self.ontology, "title")
        response = self.upload("Name;Description;datatype;sample_value\ntitle;dup;;\nyear;Year;date;1922\n;empty;;\n")
        self.assertRedirects(response, self.url("detail_ontology"))
        self.assertEqual(sorted(self.ontology.fields.values_list("name", flat=True)), ["title", "year"])
        self.assertEqual(OntologyField.objects.get(name="year").datatype, "date")

    def test_latin1_file_is_accepted(self):
        self.upload("name,description\ndescrição,Descrição do objeto\n", encoding="latin-1")
        self.assertTrue(self.ontology.fields.filter(name="descrição").exists())

    def test_single_column_file_is_accepted(self):
        self.upload("name\nyear\n")
        self.assertTrue(self.ontology.fields.filter(name="year").exists())

    def test_missing_name_column_shows_error(self):
        response = self.upload("title,description\nx,y\n")
        self.assertEqual(response.status_code, 200)
        self.assertIn("file", response.context["form"].errors)

    def test_only_the_owner_can_import(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("import_fields")).status_code, 404)


@override_settings(USE_WD_MCP=False)
@mock.patch("mapper.services.review.wikidata_api.search_properties", return_value=[])
class ReviewViewsTests(BaseViewTest):
    def setUp(self):
        super().setUp()
        self.field = make_field(self.ontology)

    def test_next_field_renders_review(self, _search):
        response = self.client.get(self.url("review"))
        self.assertEqual(response.context["field"], self.field)

    def test_redirects_to_detail_when_everything_is_done(self, _search):
        decide(self.field, MappingDecision.STATUS_INVALID)
        self.assertRedirects(self.client.get(self.url("review")), self.url("detail_ontology"))

    def test_specific_field(self, _search):
        response = self.client.get(self.url("review_field", field_id=self.field.id))
        self.assertEqual(response.status_code, 200)

    def test_decide_records_and_moves_on(self, _search):
        response = self.client.post(self.url("decide", field_id=self.field.id), {"status": "invalid"})
        self.assertRedirects(response, self.url("review"), fetch_redirect_response=False)
        self.assertEqual(MappingDecision.objects.get().status, MappingDecision.STATUS_INVALID)

    def test_review_is_closed_to_non_owners(self, _search):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("review")).status_code, 404)
        self.assertEqual(self.client.post(self.url("decide", field_id=self.field.id), {"status": "invalid"}).status_code, 404)

    @mock.patch("mapper.views.review_service.record_ai_suggestion", return_value=True)
    def test_ask_ai_saves_suggestion(self, record, _search):
        response = self.client.post(self.url("ask_ai", field_id=self.field.id), {"pid": "P580"})
        self.assertRedirects(response, self.url("review_field", field_id=self.field.id))
        record.assert_called_once()

    @mock.patch("mapper.views.review_service.record_ai_suggestion", return_value=False)
    def test_ask_ai_failure_shows_message(self, _record, _search):
        response = self.client.post(self.url("ask_ai", field_id=self.field.id), {"pid": "x"}, follow=True)
        self.assertIn("could not be saved", [str(m) for m in response.context["messages"]][0])

    def test_reset_removes_decisions(self, _search):
        decide(self.field, MappingDecision.STATUS_INVALID)
        self.assertRedirects(self.client.post(self.url("reset_ontology")), self.url("detail_ontology"))
        self.assertFalse(MappingDecision.objects.exists())


class ExportViewTests(BaseViewTest):
    def test_export_returns_zip(self):
        decide(make_field(self.ontology, sample_value="1922"), MappingDecision.STATUS_VALID, make_property())
        response = self.client.get(self.url("export"))
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_export_respects_visibility(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("export")).status_code, 404)


def addresses(*ips):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


class IsPublicHostTests(TestCase):
    @mock.patch("mapper.views.socket.getaddrinfo", return_value=addresses("8.8.8.8"))
    def test_public_address(self, _resolve):
        self.assertTrue(views.is_public_host("api.example.org"))

    @mock.patch("mapper.views.socket.getaddrinfo", return_value=addresses("8.8.8.8", "10.0.0.1"))
    def test_any_private_address_is_rejected(self, _resolve):
        self.assertFalse(views.is_public_host("mixed.example.org"))

    @mock.patch("mapper.views.socket.getaddrinfo", side_effect=socket.gaierror)
    def test_unresolvable_host(self, _resolve):
        self.assertFalse(views.is_public_host("nowhere.invalid"))


@mock.patch("mapper.views.is_public_host", return_value=True)
class AiRelayTests(BaseViewTest):
    def relay(self, url="https://api.example.org/v1", body=None, key="secret", raw=None):
        payload = raw if raw is not None else json.dumps({"url": url, "body": body if body is not None else {"model": "m"}})
        headers = {"HTTP_X_AI_KEY": key} if key else {}
        return self.client.post(reverse("ai_relay"), payload, content_type="application/json", **headers)

    def test_rejects_invalid_requests(self, _public):
        self.assertEqual(self.relay(raw="not json").status_code, 400)
        self.assertEqual(self.relay(url="http://api.example.org/v1").status_code, 400)
        self.assertEqual(self.relay(url="https://api.example.org:8443/v1").status_code, 400)
        self.assertEqual(self.relay(url="https://user:pass@api.example.org/v1").status_code, 400)
        self.assertEqual(self.relay(key="").status_code, 400)
        self.assertEqual(self.relay(body=["not", "a", "dict"]).status_code, 400)

    def test_rejects_private_hosts(self, public):
        public.return_value = False
        self.assertEqual(self.relay().status_code, 400)

    @mock.patch("mapper.views.requests.post")
    def test_forwards_once_to_chat_completions(self, post, _public):
        post.return_value = mock.Mock(content=b'{"ok": true}', status_code=200, headers={"Content-Type": "application/json"})
        response = self.relay(url="https://api.example.org/v1/chat/completions/")
        self.assertEqual(response.json(), {"ok": True})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.example.org/v1/chat/completions")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer secret"})
        self.assertFalse(kwargs["allow_redirects"])

    @mock.patch("mapper.views.requests.post", side_effect=requests.ConnectionError)
    def test_unreachable_provider(self, _post, _public):
        self.assertEqual(self.relay().status_code, 502)

    def test_requires_login(self, _public):
        self.client.logout()
        self.assertEqual(self.relay().status_code, 302)
