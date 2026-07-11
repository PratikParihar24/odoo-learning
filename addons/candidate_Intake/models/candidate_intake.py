import requests
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CandidateIntake(models.Model):
    _name = 'hr.candidate.intake'
    _description = 'Candidate Intake Record'
    
    # Existing Fields
    name = fields.Char(string='Candidate Name', required=True)
    email = fields.Char(string='Email', required=True)
    phone = fields.Char(string='Phone')
    notes = fields.Text(string='Reviewer Notes')
    
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

            applicant_vals = {
                'name': f"Intake: {record.name}",
                'partner_name': record.name,
                'email_from': record.email,
                'partner_phone': record.phone,
                'job_id': record.job_id.id if record.job_id else False,
                'description': f"AI Score: {record.ai_score}/100\n\nAI Summary:\n{record.ai_summary}\n\nReviewer Notes:\n{record.notes}",
            }
            
            new_applicant = self.env['hr.applicant'].create(applicant_vals)
            
            record.write({
                'status': 'approved',
                'applicant_id': new_applicant.id
            })

    # --- PHASE 2: AI API CALL ---
    def action_analyze_resume(self):
        for record in self:
            if not record.resume_text:
                raise UserError(_("Please paste the resume text before running AI analysis."))
            
            # For a production app, we would store this key in Odoo's ir.config_parameter settings.
            # For this build, paste your key directly here.
            api_key = self.env['ir.config_parameter'].sudo().get_param('candidate_intake.groq_api_key')
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