# Developer Interview Bible: Odoo Candidate Intake Pipeline

This document compiles the theoretical foundations, architectural designs, technical decisions, and potential interview questions for the **Candidate Intake Pipeline** Odoo 17 module.

---

## 1. Core Concepts & Tech Stack

### Odoo 17 Framework
Odoo is a suite of open-source business applications written in Python and utilizing PostgreSQL as its database backend. Odoo 17 uses an Object-Relational Mapping (ORM) layer to interface with PostgreSQL, allowing developers to define tables, relationships, and constraints in pure Python.

Key concepts in the Odoo framework:
- **Models (`models.Model`):** Define database tables. Fields are declared as Python class attributes, and Odoo translates these into database columns and constraints.
- **Views (XML):** Define the user interface (Form, Tree/List, Kanban, Search). Odoo renders these XML layouts dynamically at runtime.
- **Controllers (`http.Controller`):** Handle HTTP requests (routing), enabling frontend/website form integration.
- **Superuser (`SUPERUSER_ID`):** Odoo's admin context (`sudo()`), used to bypass access controls. Essential for forms filled out by public/unauthenticated users.
- **Chatter (`mail.thread`):** A collaboration widget that logs field updates (chatter logging) and enables notes, emails, and activities directly inside records.

### Text Extraction & PDF Manipulation
- **Base64 Encoding:** Binary data (like a PDF file) cannot be safely sent over HTML form text streams or stored raw in text fields. We base64-encode files before storing them in Odoo's binary fields.
- **PyPDF2 Library:** A pure-Python PDF library. We use `PdfReader` to extract stream characters page-by-page. Since OCR isn't applied, it reads selectable text streams from standard documents.

---

## 2. Design Patterns & Architectural Decisions

### A. The Intermediate Pipeline Pattern (Gateway Pattern)
**Decision:** Creating a distinct model (`hr.candidate.intake`) before converting candidates to official applicants (`hr.applicant`).
- **Why:** Protects Odoo's core recruitment pipeline from database noise (unscreened candidates, spam, incorrect applications).
- **How:** It acts as a gateway where candidates are screened, AI-parsed, and manually vetted before a manager promotes them to official candidates.

### B. Odoo Mixin Inheritance Pattern
**Decision:** Using `_inherit = ['mail.thread', 'mail.activity.mixin']`.
- **Why:** Avoids writing custom auditing, logging, or notifications.
- **How:** Odoo's inheritance model merges the field definitions and methods of the mixins into our custom class, instantly granting it Chatter capabilities.

### C. Attachment Cloning Pattern
**Decision:** Creating an `ir.attachment` record pointing to the `hr.applicant` model using the candidate's binary field.
- **Why:** Odoo stores documents globally in the `ir.attachment` model, using polymorphical relationships (`res_model` and `res_id`).
- **How:** Cloning the data ensures that when the candidate record is archived or removed, the recruiter maintains access to the resume inside the recruitment view.

---

## 3. Potential Technical Interview Questions & Answers

### Q1: How does Odoo's inheritance model work, and what is the difference between `_inherit` and `_inherits`?
* **Answer:** 
  * `_inherit` is used for **Extension Inheritance** (adding fields or modifying methods on an existing model) or **Mixin Inheritance** (copying features from a mixin class like `mail.thread` into a new table).
  * `_inherits` is used for **Polymorphic / Delegation Inheritance** (composition). It creates a link between two models (e.g., `res.users` inherits `res.partner` via a Many2one field), exposing all parent fields on the child model without duplicating the columns in the child's database table.

### Q2: Why did we use `sudo()` inside the controller to create the candidate record?
* **Answer:** Public website forms are executed under the context of the public/anonymous website visitor user (`public`). By default, the public user lacks write or create access to custom models (ACL rules). Calling `.sudo()` elevates the context to `SUPERUSER_ID` (system administrator), allowing database record creation without granting permanent edit privileges to public users.

### Q3: Explain how the PDF text extraction works in Odoo, and how we handle potential errors.
* **Answer:** The PDF file is stored in a Binary field as base64-encoded bytes. During execution:
  1. We retrieve and decode the base64 content: `base64.b64decode(record.resume_file)`.
  2. We wrap these bytes in an in-memory stream using `io.BytesIO`.
  3. We pass this stream to `PyPDF2.PdfReader` and concatenate text from `page.extract_text()`.
  4. The code is wrapped in a `try-except` block to gracefully fail without blocking if a user uploads a corrupted file or an image-only PDF (no selectable text).

### Q4: How is access security managed in Odoo modules?
* **Answer:** Security is managed at three levels:
  1. **Groups (`res.groups`):** Defined in XML, organizing permissions by role (e.g., Reviewer vs. Manager).
  2. **Access Control Lists (`ir.model.access.csv`):** Define read, write, create, and delete permissions for each model per group.
  3. **Record Rules (`ir.rule`):** Apply row-level domain filters on database queries (e.g., limiting a reviewer to only see records of their assigned company).
