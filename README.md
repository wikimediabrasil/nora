# NORA: Nexus of Ontologies with Reconciliation Assistance

A Django tool, hosted on [Wikimedia Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge), that helps museums, archives, libraries and research centres map the fields of their metadata ontologies to **Wikidata properties**, or to the properties of their own **Wikibase**.

Each field is reviewed one at a time. NORA brings candidate properties from a live search and, on request, an AI suggestion, but **every decision is made by a person**. Fields with no suitable property are recorded as modeling gaps and can be turned into property proposal drafts. The result is exported as an open data package ready for QuickStatements and OpenRefine reconciliation.

Developed by [Wikimedia Brasil](https://br.wikimedia.org/).

> **Status:** active (prototype, version 1.0)
>
> **Maintainers:** [EPorto (WMB)](https://meta.wikimedia.org/wiki/User:EPorto_(WMB)), Wikimedia Brasil
>
> **Production:** https://nora.toolforge.org
>
> **Questions, bugs and data requests:** [GitHub issues](https://github.com/wikimediabrasil/nora/issues)
>
> **Security reports:** see [Security](#security)
>
> **License:** code under MIT; interface text under CC BY-SA 4.0; Wikidata data under CC0
>
> **Last documentation review:** 2026-11-10

---

## Features

- **Login via OAuth**, using Wikimedia account**.
- **Mapping to Wikidata or another federated Wikibase**.
- **Field import from CSV**.
- **Field-by-field review**.
- **Candidate properties** from a live search on the Wikidata or Wikibase API and, optionally, from the [Wikidata MCP](https://www.wikidata.org/wiki/Wikidata:MCP); properties found by both sources are highlighted.
- **Optional AI help**, called only when the reviewer asks, with the reviewer's own provider and key, choosing only among the candidates on screen and always showing its justification.
- **Gaps turn into property proposal drafts**.
- **Decision history**: every change to a decision is logged.
- **Structural validation** of datatypes and constraints before the export.
- **Export as a [Frictionless Data](https://frictionlessdata.io/) package**.
- **Restrictions to ontology visibility**.

---

## Why this tool?

We could not find any documented tool that helps a user to build the ontology modeling available. QuickStatements and OpenRefine are useful tools to reconcile the items to be created on Wikidata and other wikibases, but the user still has to know which properties to create their commands.

Mapping an institution's metadata fields to Wikidata is usually done by hand and depends on advanced knowledge of Wikidata search and modeling. NORA addresses four recurring problems: a steep learning curve that limits the institutions' autonomy, modeling gaps that go unreported and contribute to a monolithic ontology, decisions that are never reused, and structural errors that reach batch-editing tools.

NORA is part of the deliverable [AI Integration for Wikimedia](https://meta.wikimedia.org/wiki/Wikimedia_Brasil/Plan_of_Activities_2026#AI_Integration_for_Wikimedia) in Wikimedia Brasil's Plan of Activities 2026, and follows a [technical development plan](https://commons.wikimedia.org/wiki/File:Ontology_Mapper_-_Technical_Development_Plan_-_en.pdf) that defines its scope and safeguards. It is also developed within:

- **[AI-BRIDGES](https://ai-bridges.org)**, a collaborative research project connecting institutions, open knowledge infrastructures and AI systems. There, NORA follows three requirements: the sovereignty of human curation, learning from past decisions, and making visible the structural gaps of Wikidata for ontologies from the Global South. The idea came from a round table at the AI-BRIDGES Symposium in May 2026.
- **[CDTIC](https://museudoipiranga.org.br/cdtic)** (Centre for Digitisation and Intelligent Treatment of Collections, FAPESP), where mapping an institution's schema to Wikidata is the first step of the round tripping workflow between collection data and the Wikimedia projects.

**Strategic link.** The tool serves the [Wikimedia Brasil Strategy 2026–2028](https://br.wikimedia.org/wiki/Estrat%C3%A9gia_Wikimedia_Brasil_2026-2028):

- Axis _Sustain collaborative practices in favor of free knowledge_, specifically action point 2: _Provide tools, resources, and training to facilitate content contribution and project sustainability_.
- Axis _Promote the Wiki methodology on the internet in Portuguese_, specifically action point 2: _Promote methodologies of democratization, collaboration, and transparency in fields such as research, open science, open data, digital infrastructure, and interdisciplinary collaboration_.

---

## How it works

### Candidates

For each field, NORA searches the ontology's endpoint (Wikidata by default, or the federated Wikibase) in the ontology's search language. When `USE_WD_MCP=1`, it also queries the Wikidata MCP hosted by Wikimedia Deutschland. Both lists are merged, and properties found by both sources come first, marked as consensus. Properties are cached locally per endpoint and PID.

### AI help

The AI call runs in the reviewer's browser, against any provider compatible with the chat completions format, including a local model on `localhost`. The AI receives the field and the candidates on screen, and can only choose among them. Its answer is saved as a suggestion, with its justification; the decision remains with the reviewer.

Some providers block calls made from the browser (CORS). For those, the browser sends the request through NORA's relay (`ai-relay/`), which only accepts HTTPS URLs resolving to public addresses and uses the key for that single request.

### Validation and export

Before export, valid decisions are checked for datatype compatibility and property constraints. The export is a zip containing:

- `mapping_quickstatements.csv`: valid decisions, compatible with QuickStatements and OpenRefine;
- `datapackage.json`: machine-readable metadata and schema;
- `REPORT.md`: readable report of what was decided and why;
- `property_proposals/*.wiki`: one property proposal draft per modeling gap, following the Wikidata preload.

---

## Roles and permissions

|                          | Public ontology | Restricted ontology | Private ontology |
|--------------------------|-----------------|---------------------|------------------|
| **Creator**              | view and edit   | view and edit       | view and edit    |
| **Superuser**            | view and edit   | view and edit       | view and edit    |
| **Listed username**      | view            | view                | —                |
| **Other logged-in user** | view            | —                   | —                |
| **Not logged in**        | —               | —                   | —                |

Editing covers importing fields, reviewing, resetting decisions and deleting the ontology. Permissions are checked on the server; an ontology the user cannot access answers as not found.

---

## Using the tool

### Create an ontology

1. Log in and click **Create new ontology mapping**.
2. Fill in the title, institution, description and **search language** (e.g. `pt`, `en`, `es`).
3. Choose the **deployment mode**. For a federated Wikibase, add its API endpoint and, if available, its SPARQL endpoint.
4. Choose the **visibility**; for restricted ontologies, list the authorized usernames.

### Import fields

On the ontology page, click **Import fields** and upload a CSV file with the columns `name`, `description`, `datatype` and `sample_value`. Only `name` is required. Rows with an empty name, or with a name already in the ontology, are skipped, so the same file can be imported again after adding rows.

### Review

On the ontology page, click **Review each field**. For each field:

1. Read the field and its candidates.
2. Optionally click **Ask AI**. The first time, enter the provider URL, model and API key; they stay in the browser tab until it closes, or until **Forget key**.
3. Record a decision: choose a candidate (valid), **No equivalent**, **Ambiguous**, or, under **More options**, manual search or **Register modeling gap**. For a gap, fill in the proposed label, datatype and justification.

Progress is shown per ontology, and the review can be split over several sessions. **Reset decisions** puts every field back in the queue.

### Export

Click **Export ontology** on the ontology page to download the Frictionless Data package.

---

## Local development

Requirements: Python 3.10+, and `gettext` for compiling translations.

```bash
git clone https://github.com/wikimediabrasil/nora.git
cd nora
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # fill in the values
```
Then:

```bash
python manage.py migrate
python manage.py compilemessages
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in with your Wikimedia account. To make yourself a superuser after the first login:

```bash
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.filter(username='YourUsername').update(is_staff=True, is_superuser=True)"
```

### OAuth consumer

Register an **OAuth 1.0a** consumer at [Special:OAuthConsumerRegistration](https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth1a) on Meta-Wiki:

- **Callback URL**: `http://127.0.0.1:8000/oauth/complete/mediawiki/`;
- tick **Allow consumer to specify a callback**;
- grants: **User identity verification only**.

Consumers usable by other accounts must be approved by a Meta-Wiki administrator, which can take a few days. Use separate consumers for development and production.

---

## Configuration and production

All configuration lives in environment variables, read from `.env` at the project root; variables already set in the environment take precedence. `.env.example` lists them all.

| Variable                | Required      | Default                              | Description                                                                                                                |
|-------------------------|---------------|--------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| `DJANGO_DEBUG`          | No            | `1`                                  | `0` in production.                                                                                                         |
| `DJANGO_SECRET_KEY`     | In production | development key                      | Required when `DJANGO_DEBUG=0`.                                                                                            |
| `DJANGO_ALLOWED_HOSTS`  | No            | `127.0.0.1,localhost`                | Comma-separated hosts.                                                                                                     |
| `DJANGO_HTTPS`          | No            | `0`                                  | `1` only in production: HTTPS redirect, secure cookies and HSTS. Keep `0` locally, since `runserver` does not serve HTTPS. |
| `OAUTH_KEY`             | Yes           |                                      | OAuth consumer key.                                                                                                        |
| `OAUTH_SECRET`          | Yes           |                                      | OAuth consumer secret.                                                                                                     |
| `OAUTH_CALLBACK`        | Yes           |                                      | Callback URL registered in the consumer.                                                                                   |
| `WIKIDATA_API_ENDPOINT` | No            | `https://www.wikidata.org/w/api.php` | Default endpoint; ontologies in Wikibase mode use their own.                                                               |
| `USE_WD_MCP`            | No            | `0`                                  | `1` adds Wikidata MCP candidates to the live search.                                                                       |
| `WD_MCP_URL`            | No            | `https://wd-mcp.wmcloud.org/mcp/`    | Wikidata MCP endpoint.                                                                                                     |

AI provider keys are not configured on the server: each reviewer uses their own, in the browser.

With `DJANGO_HTTPS=1`, Django trusts the `X-Forwarded-Proto` header set by the Toolforge proxy, and WhiteNoise serves the static files gathered by `python manage.py collectstatic` into `staticfiles/`.

---

## Project structure

```
nora/                             Django project settings and root URLs
mapper/
    models.py                     Ontology, OntologyField, WikidataProperty, MappingDecision,
                                  MappingDecisionHistory, PropertyProposal
    views.py                      ontology CRUD, import, review, AI relay, export
    forms.py                      ontology and CSV import forms
    middleware.py                 Content-Security-Policy header
    services/
        wikidata_api.py           live property search and local cache
        wikidata_mcp.py           optional Wikidata MCP client
        review.py                 review queue, candidate merging, AI suggestion
        validation.py             datatype and constraint checks
        export_quickstatements.py QuickStatements CSV
        export_frictionless.py    Frictionless Data package
    templates/                    pages of the app
templates/base.html               base layout
static/                           CSS, logos and favicons
```

---

## Translations

Interface strings are written in English and marked for translation.

```bash
python manage.py makemessages -l pt_BR
# edit locale/pt_BR/LC_MESSAGES/django.po
python manage.py compilemessages
```

The language follows the browser; `LANGUAGE_CODE` in `settings.py` sets the default (English).

---

## Personal data and privacy (LGPD)

The tool follows the ABPD principle *privacy from the start*: it collects only what mapping and review require.

| Data                                   | Where                                                                                  | Purpose                            | Who can see it                                |
|----------------------------------------|----------------------------------------------------------------------------------------|------------------------------------|-----------------------------------------------|
| Wikimedia username                     | Django user                                                                            | identify reviewers and owners      | users who can view the ontology               |
| OAuth tokens returned by Meta-Wiki     | `social_django` tables                                                                 | complete the login                 | nobody through the interface                  |
| Authorship of ontologies and decisions | `Ontology` (`created_by`, `updated_by`), `MappingDecision` and history (`reviewed_by`) | record who decided what            | users who can view the ontology               |
| Authorized usernames                   | `Ontology`                                                                             | restrict access                    | the ontology's creator and superusers         |
| AI provider URL, model and key         | browser tab (`sessionStorage`)                                                         | call the AI chosen by the reviewer | the reviewer only; erased when the tab closes |
| Session cookie                         | browser                                                                                | keep the user logged in            | —                                             |

- **Not collected:** e-mail, real name, IP addresses (the OAuth grant is *User identity verification only*; Toolforge's own infrastructure logs are governed by the Wikimedia Cloud Services terms).
- **Sent to third parties:** when the reviewer asks for AI help, the field's name, description, sample value and candidates go to the provider the reviewer chose. Do not import fields whose sample values contain personal data.
- **RIPD:** not required

---

## Security

- CSRF protection on every form (Django middleware), including login and logout.
- All database access goes through the Django ORM (parameterised queries); templates auto-escape output.
- Permissions checked on the server.
- Views declare the HTTP methods they accept; data only changes through POST.
- The AI relay accepts only HTTPS URLs on the default port, without credentials in the URL, resolving to public addresses, and does not follow redirects. The key is used for a single request and kept out of error reports (`@sensitive_variables`).
- A `Content-Security-Policy` header limits where page scripts can send data: NORA itself, HTTPS sites, or a local model.
- External assets come only from `tools-static.wmflabs.org`.
- Secrets live in environment variables and are never committed; `.env` is in `.gitignore`. **Rotate** `DJANGO_SECRET_KEY` and the OAuth consumer secret whenever a maintainer leaves the project.
- **Reporting vulnerabilities:** contact the maintainers. Issues affecting Toolforge itself follow the [Wikimedia Foundation security process](https://www.mediawiki.org/wiki/Reporting_security_bugs).

---

## Accessibility

- Review actions are real `<button>` elements with text labels; decorative icons are hidden from screen readers (`aria-hidden`).
- The tool follows WCAG 2.0 level AA for contrast, and we used WAVE - web accessibility evaluation tool to test every page.

---

## Discontinuation

- **Discontinuation plan:** export the mapping package of every ontology and hand it to the owning institutions, apply the retention rule above, drop the database, stop the webservice, revoke the OAuth consumer, and mark the tool as *discontinued* in the WMB tool catalog and in this repository.

---

## Use of AI in development

Base code was implemented with substantial help from an AI assistant (Claude, from Anthropic) and extensively reviewed and refactored by a human developer.
Brazilian Portuguese translation was done by an AI assistant and reviewed by a human.

---

## Contributing

Good first tasks:

- automated tests for `validation.py` and the export services;
- tests for the access rules in `Ontology.can_view` and `Ontology.can_edit`;
- tests for the AI relay's URL checks;
- tests and evaluation for MCP results in different languages;
- a GitHub Actions workflow running the tests, and Dependabot alerts.

Changes are reviewed by a second person before deployment; when no reviewer is available, record the decision and the reason in the pull request.

---

## ABPD self-assessment

Assessment against the [Development Best Practices Framework](https://meta.wikimedia.org/wiki/Wikimedia_Brasil/Development_Best_Practices_Framework) (section 5.11). Reviewed on 2026-11-10.

| #       | Criterion                                       | Status      | What is missing                     |
|---------|-------------------------------------------------|-------------|-------------------------------------|
| 5.11.1  | Public repository and declared free license     | **Present** | —                                   |
| 5.11.2  | README with purpose, installation and execution | **Present** | —                                   |
| 5.11.3  | Configuration and production documentation      | **Present** | —                                   |
| 5.11.4  | Automated tests for critical functions          | **Absent**  | All the tests                       |
| 5.11.5  | Continuous integration                          | **Absent**  | GitHub Actions workflow             |
| 5.11.6  | Reproducible and documented deployment          | **Present** | —                                   |
| 5.11.7  | Secrets out of the code, with planned rotation  | **Present** | —                                   |
| 5.11.8  | Maintainer identified                           | **Present** | —                                   |
| 5.11.9  | More than one person able to maintain it        | **Absent**  | a second maintainer                 |
| 5.11.10 | Minimum security checklist applied              | **Present** | —                                   |
| 5.11.11 | Basic accessibility verified                    | **Present** | —                                   |
| 5.11.12 | Translatable interface text                     | **Present** | —                                   |
| 5.11.13 | Substantial AI use recorded                     | **Present** | —                                   |
| 5.11.14 | Personal data mapped; RIPD where applicable     | **Present** | —                                   |
| 5.11.15 | Backup and recovery                             | **Absent**  | backup routine and a tested restore |
| 5.11.16 | Status declared                                 | **Present** | —                                   |
