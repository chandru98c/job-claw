from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mock-ats", tags=["mock-ats"])

@router.get("/job/{job_id}/apply", response_class=HTMLResponse)
async def get_mock_apply_form(job_id: str, fail: bool = False, unknown: bool = False):
    """
    Returns a deterministic mock HTML form for E2E application testing.
    """
    print(f"MOCK ATS GET /job/{job_id}/apply called (fail={fail}, unknown={unknown})")
    query = ""
    if fail:
        query = "?fail=true"
    elif unknown:
        query = "?unknown=true"
        
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Apply to Job {job_id}</title></head>
    <body>
        <h1>Apply for Job {job_id}</h1>
        <form method="POST" action="/mock-ats/job/{job_id}/apply{query}">
            <label for="first_name">First Name</label>
            <input type="text" id="first_name" name="first_name" required>
            
            <label for="last_name">Last Name</label>
            <input type="text" id="last_name" name="last_name" required>
            
            <label for="email">Email</label>
            <input type="email" id="email" name="email" required>
            
            <label for="resume">Resume</label>
            <input type="file" id="resume" name="resume">
            
            <label for="why_work_here">Why do you want to work here?</label>
            <textarea id="why_work_here" name="why_work_here" required></textarea>
            
            <button type="submit">Submit Application</button>
        </form>
    </body>
    </html>
    """
    return html

@router.post("/job/{job_id}/apply", response_class=HTMLResponse)
async def submit_mock_apply_form(request: Request, job_id: str, fail: bool = False, unknown: bool = False):
    """
    Accepts the mock application submission.
    """
    if fail:
        return HTMLResponse(content="<h1>Internal Server Error</h1><p>Simulated failure</p>", status_code=500)
    
    if unknown:
        # Return a response that the worker can't parse as success or failure
        return HTMLResponse(content="<h1>Under Review</h1><p>We will get back to you.</p>", status_code=200)

    form_data = await request.form()
    logger.info(f"Mock ATS received application for {job_id}: {dict(form_data)}")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Application Received</title></head>
    <body>
        <h1>Success</h1>
        <p>Application for job {job_id} has been received.</p>
        <div id="reference_id">MOCK-REF-12345</div>
    </body>
    </html>
    """
    return html
