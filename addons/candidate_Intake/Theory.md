# Developer Interview Bible: Candidate Intake Pipeline (Odoo 17)

This document covers every concept, pattern, and design decision in the project — written as interview preparation material. Each section includes the theory, how it applies to this codebase, and practice questions with answers.

---

## 1. Odoo Framework Fundamentals

### 1.1 The ORM (Object-Relational Mapping)

**Theory:** Odoo's ORM maps Python classes to PostgreSQL tables. When you define `_name = 'hr.candidate.intake'`, Odoo creates a table called `hr_candidate_intake` (dots become underscores). Each class attribute using `fields.*` becomes a database column.

**In this project:** [candidate_intake.py:6-8](file:///c:/odoo_learning/addons/candidate_Intake/models/candidate_intake.py#L6-L8) defines the model. The ORM handles all SQL — `record.write({...})` generates an `UPDATE` statement, `self.env['hr.applicant'].create({...})` generates an `INSERT`.

### 1.2 Field Types Used

| Field Type | Python Class | PostgreSQL Type | Example in Project |
|-----------|-------------|----------------|-------------------|
| `Char` | `fields.Char` | `VARCHAR` | `name`, `email`, `linkedin_url` |
| `Text` | `fields.Text` | `TEXT` | `resume_text`, `ai_summary`, `ai_strengths`, `ai_missing_skills` |
| `Integer` | `fields.Integer` | `INTEGER` | `ai_score` |
| `Binary` | `fields.Binary` | Stored in `ir.attachment` | `resume_file` (with `attachment=True`) |
| `Selection` | `fields.Selection` | `VARCHAR` | `status`, `source` |
| `Many2one` | `fields.Many2one` | `INTEGER` (FK) | `job_id → hr.job`, `applicant_id → hr.applicant` |

### 1.3 Module Manifest

**Theory:** Every Odoo module must have a `__manifest__.py` file. It declares the module's name, version, dependencies, and which data files to load during installation/upgrade.

**In this project:** [__manifest__.py](file:///c:/odoo_learning/addons/candidate_Intake/__manifest__.py) lists `depends: ['base', 'hr', 'hr_recruitment', 'website', 'mail']`. This means Odoo will refuse to install our module unless all five dependencies are already installed. The `data` list controls the load order — security files load before views because views reference security groups.

---

## 2. Architecture & Design Patterns

### 2.1 Gateway / Intermediate Pipeline Pattern

**What it is:** Instead of feeding raw applications directly into the production recruitment pipeline (`hr.applicant`), we introduce a staging table (`hr.candidate.intake`) that acts as a filter.

**Why it matters:**
- Protects the recruitment pipeline from noise (spam, unqualified candidates, incomplete applications).
- Allows AI scoring and human review before data enters the official pipeline.
- Prevents accidental deletion or modification of sensitive recruitment records.

**Interview angle:** This pattern is analogous to a message queue or staging environment in microservices — you validate and transform data before committing it to the production system.

### 2.2 State Machine Pattern

**What it is:** The `status` field defines a finite set of states (`new → review → approved/rejected`). Each action method enforces valid transitions with guard clauses.

**In this project:**
```python
# Guard clause example from action_approve (line 62)
if record.status != 'review':
    raise UserError(_("You can only approve candidates currently 'Under Review'."))
```

**Why not use Odoo's built-in `states` attribute?** Odoo 17 deprecated the `states` attribute on fields. The explicit if-checks are cleaner, more readable, and testable.

### 2.3 Mixin Inheritance Pattern

**What it is:** Python multiple inheritance where abstract base classes provide reusable functionality without creating their own database tables.

**In this project:** [candidate_intake.py:9](file:///c:/odoo_learning/addons/candidate_Intake/models/candidate_intake.py#L9):
```python
_inherit = ['mail.thread', 'mail.activity.mixin']
```

This single line gives our model:
- **Chatter widget** (message log, followers, file attachments)
- **Activity scheduling** (to-do reminders linked to records)
- **Field tracking** (automatic log entries when tracked fields change)

**Key distinction:** `_inherit` with `_name` defined = new model using mixins. `_inherit` without `_name` = extending an existing model.

### 2.4 Polymorphic Attachment Pattern

**What it is:** Odoo's `ir.attachment` model uses two fields — `res_model` (string) and `res_id` (integer) — to link any file to any record in any model. This is a form of polymorphic association.

**In this project:** [candidate_intake.py:90-95](file:///c:/odoo_learning/addons/candidate_Intake/models/candidate_intake.py#L90-L95):
```python
self.env['ir.attachment'].create({
    'name': record.resume_filename or 'resume.pdf',
    'datas': record.resume_file,
    'res_model': 'hr.applicant',
    'res_id': new_applicant.id,
})
```

The resume PDF is duplicated as a new attachment record pointing to the applicant, making it visible in the Recruitment app's sidebar.

---

## 3. Web Controllers & HTTP in Odoo

### 3.1 Route Decorators

**Theory:** `@http.route()` registers a URL path with Odoo's HTTP dispatcher. Key parameters:

| Parameter | Value in Project | Meaning |
|-----------|-----------------|---------|
| `type` | `'http'` | Standard HTTP request (vs `'json'` for JSON-RPC) |
| `auth` | `'public'` | No login required |
| `website` | `True` | Uses the website layout/theme |
| `methods` | `['POST']` | Restrict to POST only (for the submit route) |

### 3.2 File Upload Handling

**Theory:** HTML forms with `enctype="multipart/form-data"` send binary files as separate MIME parts. In Odoo, the raw Werkzeug request is accessed via `request.httprequest`.

**In this project:** [main.py:18-23](file:///c:/odoo_learning/addons/candidate_Intake/controllers/main.py#L18-L23):
```python
file_upload = request.httprequest.files.get('resume_file')  # Werkzeug FileStorage
resume_file = base64.b64encode(file_upload.read())           # bytes → base64 for Odoo Binary field
resume_filename = file_upload.filename                        # preserve original name
```

### 3.3 CSRF Protection

**Theory:** Cross-Site Request Forgery tokens prevent malicious sites from submitting forms on behalf of authenticated users. Odoo generates a unique token per session.

**In this project:** [website_form.xml:8](file:///c:/odoo_learning/addons/candidate_Intake/views/website_form.xml#L8):
```xml
<input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
```

### 3.4 The `sudo()` Bypass

**Theory:** `sudo()` returns a new recordset operating under `SUPERUSER_ID`, bypassing all access control rules. This is necessary when anonymous/public users need to create records they wouldn't normally have permission to create.

**Security implication:** `sudo()` should only be used with sanitized, validated input. Never pass raw user input to `sudo().write()` on sensitive models.

---

## 4. PDF Text Extraction

### 4.1 The Binary → Text Pipeline

```
Odoo Binary field (base64 string)
    → base64.b64decode() → raw bytes
    → io.BytesIO() → file-like stream
    → PyPDF2.PdfReader() → PDF object
    → page.extract_text() → plain text string
    → saved to resume_text field
```

### 4.2 PyPDF2 API (v3.0.1)

| Old API (v1.x) | Modern API (v3.x) | Used in Project |
|----------------|-------------------|-----------------|
| `PdfFileReader(stream)` | `PdfReader(stream)` | ✅ Modern |
| `reader.numPages` | `len(reader.pages)` | ✅ Modern |
| `reader.getPage(n)` | `reader.pages[n]` | ✅ Modern (iteration) |
| `page.extractText()` | `page.extract_text()` | ✅ Modern |

### 4.3 Limitations

- **Image-only PDFs** (scanned documents) will return empty text — PyPDF2 does not include OCR.
- **Complex layouts** (multi-column, tables) may produce garbled text ordering.
- The code silently handles failures via `try-except` to avoid blocking the user.

---

## 5. AI Integration (Groq API)

### 5.1 Architecture

```
Odoo Server → HTTPS POST → Groq API (api.groq.com)
                         → llama-3.1-8b-instant model
                         → JSON response (forced via response_format)
                         → parsed and written to ORM fields
```

### 5.2 Prompt Engineering

The prompt uses a **weighted rubric** scoring system:

| Criterion | Weight | What it evaluates |
|-----------|--------|-------------------|
| Skill Match | 35 pts | Technical and soft skills alignment |
| Relevant Experience | 35 pts | Past work history relevance |
| Measurable Impact | 20 pts | Quantifiable achievements vs. generic duties |
| Professionalism | 10 pts | Resume structure, clarity, relevance |

**Scoring bands** enforce realistic distributions:
- 90-100: Exceptional (top 1%)
- 75-89: Strong
- 50-74: Average/Entry
- 0-49: Poor Fit

The response is forced into a structured JSON schema with four fields: `summary`, `score`, `strengths`, `missing`.

### 5.3 API Key Management

The API key is stored in Odoo's `ir.config_parameter` (System Parameters), not hardcoded. This follows the **externalized configuration** pattern — the key can be changed at runtime without redeploying code.

---

## 6. Security Model Deep Dive

### 6.1 Three Layers of Odoo Security

| Layer | Mechanism | Granularity | File |
|-------|-----------|------------|------|
| Groups | `res.groups` records | Role-based | [security.xml](file:///c:/odoo_learning/addons/candidate_Intake/security/security.xml) |
| ACL | `ir.model.access` CSV | Model-level (CRUD per group) | [ir.model.access.csv](file:///c:/odoo_learning/addons/candidate_Intake/security/ir.model.access.csv) |
| Record Rules | `ir.rule` records | Row-level (domain filters) | [security.xml](file:///c:/odoo_learning/addons/candidate_Intake/security/security.xml#L24-L29) |

### 6.2 Group Inheritance

```
Manager ──inherits──→ Reviewer
```

`implied_ids = [(4, ref('group_intake_reviewer'))]` means any user assigned to the Manager group automatically gets all Reviewer permissions too. The `(4, id)` is Odoo's ORM command for adding a Many2many link.

### 6.3 Button-Level Security

The "Approve & Convert" button in XML uses `groups="candidate_Intake.group_intake_manager"` — Odoo completely hides this button from users who don't belong to the Manager group. This is a UI-level guard; the server-side method itself doesn't check groups (it trusts the ACL layer).

---

## 7. Practice Interview Questions & Answers

### Q1: What is the difference between `_inherit` and `_inherits` in Odoo?

**Answer:**
- `_inherit` (single underscore s) is used for **class inheritance**: either extending an existing model (no `_name` = adds fields/methods to the parent) or mixing in abstract classes (with `_name` = new model that copies mixin behavior). In our project, we use `_inherit = ['mail.thread', 'mail.activity.mixin']` with `_name = 'hr.candidate.intake'` — this creates a new table while pulling in chatter functionality.
- `_inherits` (double s) is **delegation inheritance** — it creates a Many2one link to a parent model and exposes all parent fields transparently. Example: `res.users` inherits `res.partner` via delegation, so every user record automatically has a linked partner record.

### Q2: Why do you use `sudo()` in the website controller but not in the backend action methods?

**Answer:** The website form is submitted by anonymous public users who have zero database permissions. Without `sudo()`, the `create()` call would raise an `AccessError`. In contrast, backend action methods (like `action_approve`) are triggered by logged-in users who already have ACL permissions through their assigned security groups. Using `sudo()` there would bypass the security model we carefully defined.

### Q3: How does Odoo know which database columns to create when you upgrade a module?

**Answer:** During module upgrade (`-u`), Odoo's module loading system compares the Python field definitions in the model class against the actual PostgreSQL table schema. For each new `fields.*` attribute, it runs an `ALTER TABLE ADD COLUMN` statement. For changed field properties (like adding `tracking=True`), it updates the `ir.model.fields` registry. This is why you must run the upgrade command after adding new fields — simply restarting the server only reloads Python code, not the database schema.

### Q4: Explain the full lifecycle of a PDF file from upload to appearing in the Recruitment pipeline.

**Answer:**
1. The browser sends the raw file bytes as a multipart form upload.
2. The controller reads the Werkzeug `FileStorage` object and encodes it to base64 (required by Odoo's Binary field type).
3. The base64 string is stored in the `resume_file` column (or as an `ir.attachment` because `attachment=True`).
4. When "Run AI Analysis" is clicked, the base64 is decoded back to bytes, wrapped in a `BytesIO` stream, and fed to `PyPDF2.PdfReader` for text extraction.
5. When "Approve & Convert" is clicked, a new `ir.attachment` record is created with `res_model='hr.applicant'` and `res_id=<new applicant ID>`, copying the base64 data. This makes the file appear in the Recruitment app's form view attachments panel.

### Q5: What would happen if you removed the `tracking=True` parameter from the `status` field?

**Answer:** The Chatter widget would stop logging automatic messages like "Status changed from New to Under Review." The field would still function normally — users could still change the status — but there would be no audit trail. The `tracking` parameter registers a post-write hook in `mail.thread` that compares old and new values and posts a `mail.message` record to the chatter if they differ.

### Q6: Why did you store the API key in `ir.config_parameter` instead of hardcoding it?

**Answer:** Three reasons:
1. **Security:** Hardcoded keys end up in version control (git). System Parameters are stored in the database, not in source files.
2. **Flexibility:** The key can be rotated at runtime through Settings → System Parameters without a code deployment.
3. **Environment separation:** Different Odoo databases (dev, staging, production) can use different API keys without code changes.

### Q7: What is the `response_format: {"type": "json_object"}` parameter doing in the Groq API call?

**Answer:** This activates Groq's **structured output mode** (also called JSON mode). It constrains the LLM to always produce valid JSON in its response, preventing free-text answers that would cause `json.loads()` to throw a `JSONDecodeError`. Without this, the model might respond with conversational text like "Here's my analysis:" followed by unstructured content, breaking the parsing logic.

### Q8: Explain the `(4, ref('group_intake_reviewer'))` syntax in the security XML.

**Answer:** This is Odoo's ORM command syntax for Many2many field operations. The tuple `(4, id)` means "add an existing record with this ID to the relation without removing others." In context, it's saying "the Manager group implies (includes) the Reviewer group." Other common commands: `(3, id)` = remove link, `(5, 0, 0)` = remove all links, `(6, 0, [ids])` = replace all links with this list.
