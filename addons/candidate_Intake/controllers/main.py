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
        # sudo() bypasses security since the public user is anonymous
        request.env['hr.candidate.intake'].sudo().create({
            'name': post.get('name'),
            'email': post.get('email'),
            'phone': post.get('phone'),
            'job_id': int(post.get('job_id')) if post.get('job_id') else False,
            'resume_text': post.get('resume_text'),
            'source': 'other',
        })
        return request.render('candidate_Intake.apply_success_template', {})