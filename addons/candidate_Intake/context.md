# Technical Context: Candidate Intake Pipeline (Odoo 17)

This document is the single source of truth for the architecture, module design, and technical internals of the **Candidate Intake Pipeline** custom Odoo 17 module.

---

## Repository Overview

```
odoo_learning/
├── docker-compose.yml          # Docker services: Odoo 17 web + PostgreSQL 15
└── addons/
    └── candidate_Intake/
        ├── __init__.py               # Root package init (imports controllers, models)
        ├── __manifest__.py           # Module manifest: metadata, dependencies, data files
        ├── controllers/
        │   ├── __init__.py           # Controller package init
        │   └── main.py              # HTTP routes: /jobs/apply (GET) and /jobs/submit (POST)
        ├── models/
        │   ├── __init__.py           # Models package init
        │   └── candidate_intake.py   # Core ORM model, state machine, PDF extraction, Groq AI
        ├── security/
        │   ├── ir.model.access.csv   # ACL: Reviewer (R/W/C) and Manager (R/W/C/D)
        │   └── security.xml          # Group definitions, module category, record rules
        ├── views/
        │   ├── candidate_intake_views.xml  # Backend: tree, form (with chatter), action, menu
        │   └── website_form.xml      # Frontend: public apply form + success page
        ├── context.md                # This file
        ├── UserJourney.md            # End-to-end user & data flow handbook
        └── Theory.md                 # Interview preparation & concept reference
```

---

## Infrastructure

| Component | Technology | Details |
|-----------|-----------|---------|
| ERP Framework | Odoo 17 Community | Docker image `odoo:17.0` |
| Database | PostgreSQL 15 | Docker image `postgres:15`, user/pass: `odoo/odoo` |
| AI Backend | Groq API | Model: `llama-3.1-8b-instant`, JSON response mode |
| PDF Parsing | PyPDF2 3.0.1 | `PdfReader` API, installed manually in container |
| Deployment | Docker Compose | Addons mounted at `/mnt/extra-addons`, DB volume persisted |

---

## Module Manifest (`__manifest__.py`)

- **Name:** Candidate Intake Pipeline
- **Category:** Human Resources/Recruitment
- **Dependencies:** `base`, `hr`, `hr_recruitment`, `website`, `mail`
- **Application:** `False` — it extends the Recruitment app, not a standalone module
- **License:** LGPL-3

---

## Data Model: `hr.candidate.intake`

**Mixins inherited:** `mail.thread`, `mail.activity.mixin`

### Field Reference

| Field | Type | Purpose | Extras |
|-------|------|---------|--------|
| `name` | Char | Candidate's full name | required, tracking |
| `email` | Char | Candidate's email | required, tracking |
| `phone` | Char | Phone number | — |
| `linkedin_url` | Char | LinkedIn profile URL | — |
| `degree` | Char | Academic degree | — |
| `resume_file` | Binary | Uploaded PDF resume | attachment=True |
| `resume_filename` | Char | Original filename | — |
| `source` | Selection | How the candidate arrived | manual / referral / other |
| `status` | Selection | Pipeline state | new → review → approved / rejected, tracking |
| `job_id` | Many2one | Target position | → `hr.job` |
| `applicant_id` | Many2one | Converted applicant link | → `hr.applicant`, readonly |
| `resume_text` | Text | Extracted plain text from PDF | — |
| `ai_summary` | Text | AI-generated 3-sentence summary | readonly |
| `ai_strengths` | Text | AI-identified top strengths | readonly |
| `ai_missing_skills` | Text | AI-identified skill gaps | readonly |
| `ai_score` | Integer | AI match score (0–100) | readonly |

### State Machine

```
NEW  ──→  UNDER REVIEW  ──→  APPROVED  (creates hr.applicant)
                         ──→  REJECTED
```

### Business Logic Methods

| Method | Trigger | What it does |
|--------|---------|-------------|
| `action_start_review` | "Start Review" button | Validates `new` → writes `review` |
| `action_reject` | "Reject" button | Validates `review` → writes `rejected` |
| `action_approve` | "Approve & Convert" button | Creates `hr.applicant` with mapped fields + `ir.attachment` for resume, resolves/creates `hr.recruitment.degree`, writes `approved` |
| `action_analyze_resume` | "Run AI Analysis" button | Extracts PDF text via PyPDF2, calls Groq LLM, writes `ai_summary`, `ai_strengths`, `ai_missing_skills`, `ai_score` |

---

## Controller Routes (`controllers/main.py`)

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/jobs/apply` | GET | public | Renders the application form with job position dropdown |
| `/jobs/submit` | POST | public | Processes multipart form, base64-encodes resume, creates intake record via `sudo()` |

---

## Security Model

### Groups (defined in `security.xml`)
- **Reviewer** (`group_intake_reviewer`): Base role for reviewing candidates
- **Manager** (`group_intake_manager`): Inherits Reviewer, can approve/convert and delete records

### ACL Permissions (`ir.model.access.csv`)

| Group | Read | Write | Create | Delete |
|-------|------|-------|--------|--------|
| Reviewer | ✅ | ✅ | ✅ | ❌ |
| Manager | ✅ | ✅ | ✅ | ✅ |

### Record Rules
- Managers see all records (domain: `[(1, '=', 1)]`)

---

## AI Integration Details

- **API:** Groq Chat Completions (`https://api.groq.com/openai/v1/chat/completions`)
- **Model:** `llama-3.1-8b-instant`
- **API Key Storage:** `ir.config_parameter` key: `candidate_intake.groq_api_key`
- **Response Format:** Forced JSON mode (`response_format: {type: "json_object"}`)
- **Temperature:** 0.2 (deterministic scoring)
- **Scoring Rubric:** 4-criteria weighted evaluation (Skill Match 35pts, Experience 35pts, Impact 20pts, Professionalism 10pts)
- **Output Fields:** `summary`, `score`, `strengths`, `missing`

---

## Key Odoo Upgrade Command

Because the module database is `test_db` (not the default), upgrades require explicit credentials:

```bash
docker compose exec web odoo --db_host=db --db_user=odoo --db_password=odoo -d test_db -u candidate_Intake --stop-after-init
docker compose restart web
```
