import requests
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CandidateIntake(models.Model):
    _name = 'hr.candidate.intake'
    _description = 'Candidate Intake Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    # Existing Fields
    name = fields.Char(string='Candidate Name', required=True, tracking=True)
    email = fields.Char(string='Email', required=True, tracking=True)
    phone = fields.Char(string='Phone')
    notes = fields.Text(string='Reviewer Notes')
    
    # New Fields
    linkedin_url = fields.Char(string="LinkedIn Profile")
    degree = fields.Char(string="Degree")
    resume_file = fields.Binary(string="Resume Document", attachment=True)
    resume_filename = fields.Char(string="File Name")
    
    source = fields.Selection([
        ('manual', 'Manual Entry'),
        ('referral', 'Referral'),
        ('other', 'Other')
    ], string='Source', default='manual')
    
    status = fields.Selection([
        ('new', 'New'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Status', default='new', tracking=True)
    
    job_id = fields.Many2one('hr.job', string='Target Job Position')
    applicant_id = fields.Many2one('hr.applicant', string='Linked Applicant', readonly=True)

    # --- PHASE 2: AI FIELDS ---
    resume_text = fields.Text(string="Resume Text (Paste Here)")
    ai_summary = fields.Text(string="AI Summary", readonly=True)
    ai_score = fields.Integer(string="AI Match Score (0-100)", readonly=True)

    # --- ACTION METHODS ---

    def action_start_review(self):
        for record in self:
            if record.status != 'new':
                raise UserError(_("You can only start review on 'New' records."))
            record.status = 'review'

    def action_reject(self):
        for record in self:
            if record.status != 'review':
                raise UserError(_("You can only reject candidates currently 'Under Review'."))
            record.status = 'rejected'

    def action_approve(self):
        for record in self:
            if record.status != 'review':
                raise UserError(_("You can only approve candidates currently 'Under Review'."))
            if record.applicant_id:
                raise UserError(_("This candidate has already been converted to an applicant."))

            # Find or create degree in hr.recruitment.degree
            degree_id = False
            if record.degree:
                degree = self.env['hr.recruitment.degree'].sudo().search([('name', '=ilike', record.degree.strip())], limit=1)
                if not degree:
                    degree = self.env['hr.recruitment.degree'].sudo().create({'name': record.degree.strip()})
                degree_id = degree.id

            applicant_vals = {
                'name': f"Intake: {record.name}",
                'partner_name': record.name,
                'email_from': record.email,
                'partner_phone': record.phone,
                'job_id': record.job_id.id if record.job_id else False,
                'linkedin_profile': record.linkedin_url,
                'type_id': degree_id,
                'description': f"AI Score: {record.ai_score}/100\n\nAI Summary:\n{record.ai_summary}\n\nReviewer Notes:\n{record.notes}",
            }
            
            new_applicant = self.env['hr.applicant'].create(applicant_vals)
            
            # Copy attachment
            if record.resume_file:
                self.env['ir.attachment'].create({
                    'name': record.resume_filename or 'resume.pdf',
                    'datas': record.resume_file,
                    'res_model': 'hr.applicant',
                    'res_id': new_applicant.id,
                })
            
            record.write({
                'status': 'approved',
                'applicant_id': new_applicant.id
            })

    # --- PHASE 2: AI API CALL ---
    def action_analyze_resume(self):
        for record in self:
            if record.resume_file:
                import io
                import base64
                import PyPDF2
                try:
                    pdf_bytes = base64.b64decode(record.resume_file)
                    pdf_file = io.BytesIO(pdf_bytes)
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += (page.extract_text() or "") + "\n"
                    if text.strip():
                        record.resume_text = text.strip()
                except Exception as e:
                    pass

            if not record.resume_text:
                raise UserError(_("Please upload a valid PDF resume or ensure there is text in the Resume Text field before running AI analysis."))
            
            api_key = self.env['ir.config_parameter'].sudo().get_param('candidate_intake.groq_api_key')
            if not api_key:
                raise UserError(_("Groq API Key is not configured. Please set the 'candidate_intake.groq_api_key' parameter in System Parameters."))
            url = "https://api.groq.com/openai/v1/chat/completions"
            
            job_title = record.job_id.name if record.job_id else "a general position"
            
            prompt = f"""
            Analyze the following resume for the position of {job_title}.
            Provide a brief 3-sentence summary of their qualifications, and assign a match score from 0 to 100.
            Respond strictly in valid JSON format like this: {{"summary": "...", "score": 85}}.
            
            Resume:
            {record.resume_text}
            """
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama-3.1-8b-instant", 
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=15)
                
                # If Groq rejects it, show the exact error message from Groq's servers
                if response.status_code != 200:
                    raise UserError(_(f"Groq API Error {response.status_code}: {response.text}"))
                
                result = response.json()
                content_str = result['choices'][0]['message']['content']
                ai_data = json.loads(content_str)
                
                record.write({
                    'ai_summary': ai_data.get('summary', 'No summary generated.'),
                    'ai_score': int(ai_data.get('score', 0))
                })
                
            except requests.exceptions.RequestException as e:
                raise UserError(_(f"Failed to connect to Groq API: {str(e)}"))
            except json.JSONDecodeError:
                raise UserError(_("The AI did not return a valid JSON format. Please try again."))