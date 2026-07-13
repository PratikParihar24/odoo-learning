{
    'name': 'Candidate Intake Pipeline',
    'version': '1.0',
    'category': 'Human Resources/Recruitment',
    'summary': 'Structured candidate intake and review before formal application',
    'description': """
        Adds an intermediate review stage for candidates before they are converted 
        into official applicants in the Recruitment pipeline.
    """,
    'author': 'Pratik',
    'depends': ['base', 'hr', 'hr_recruitment', 'website', 'mail'], 
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/candidate_intake_views.xml',
        'views/website_form.xml',
    ],
    'installable': True,
    'application': False, # It's an extension, not a standalone app
    'license': 'LGPL-3',
}