import base64
from odoo import http
from odoo.http import request

class CandidateIntakeController(http.Controller):
    
    # Route 1: Displays the form
    @http.route('/jobs/apply', type='http', auth='public', website=True)
    def intake_form(self, **kwargs):
        # Fetch active job positions to populate the dropdown
        jobs = request.env['hr.job'].sudo().search([])
        return request.render('candidate_Intake.apply_form_template', {'jobs': jobs})

    # Route 2: Handles the form submission
    @http.route('/jobs/submit', type='http', auth='public', website=True, methods=['POST'])
    def intake_submit(self, **post):
        # Capture the uploaded file
        file_upload = request.httprequest.files.get('resume_file')
        resume_file = False
        resume_filename = False
        if file_upload:
            resume_file = base64.b64encode(file_upload.read())
            resume_filename = file_upload.filename

        # sudo() bypasses security since the public user is anonymous
        request.env['hr.candidate.intake'].sudo().create({
            'name': post.get('name'),
            'email': post.get('email'),
            'phone': post.get('phone'),
            'job_id': int(post.get('job_id')) if post.get('job_id') else False,
            'source': 'other',
            'linkedin_url': post.get('linkedin_url'),
            'degree': post.get('degree'),
            'resume_file': resume_file,
            'resume_filename': resume_filename,
        })
        return request.render('candidate_Intake.apply_success_template', {})