import logging
from typing import Optional, Dict, Any, List
from app.application.browser import ApplicationBrowser
from app.schemas.application import ApplicationDraft, ApplicationField, FieldSource
from app.application.mapper import ProfileFieldMapper
from app.database.models import Profile

logger = logging.getLogger(__name__)

class GreenhouseApplicationAdapter:
    """
    Handles extracting forms and mapping them for Greenhouse ATS.
    """
    def __init__(self, browser: ApplicationBrowser):
        self.browser = browser
        
    async def prepare_draft(self, application_id: str, job_id: str, profile: Profile, apply_url: str) -> Optional[ApplicationDraft]:
        logger.info(f"Greenhouse: Inspecting form for {apply_url}")
        
        inspection = await self.browser.inspect_form(apply_url)
        if not inspection.get("success"):
            logger.error(f"Failed to inspect form: {inspection.get('reason')}")
            return None
            
        form_fields = inspection.get("fields", [])
        
        # Map profile fields
        mapped_fields = ProfileFieldMapper.map_fields(profile, form_fields)
        
        unanswered = [
            f.field_id for f in mapped_fields 
            if f.required and f.source == FieldSource.REQUIRES_USER_INPUT
        ]
        
        draft = ApplicationDraft(
            application_id=application_id,
            job_id=job_id,
            destination=apply_url,
            fields=mapped_fields,
            unanswered_required_fields=unanswered,
            resume_reference=profile.resume_path,
            ready_for_submission=len(unanswered) == 0
        )
        return draft
        
    async def submit_draft(self, apply_url: str, fields: List[ApplicationField]) -> Dict[str, Any]:
        logger.info(f"Greenhouse: Submitting application to {apply_url}")
        
        filled = [
            {
                "id": f.field_id,
                "label": f.label,
                "type": f.type,
                "value": f.value
            }
            for f in fields
        ]
        
        return await self.browser.submit_form(apply_url, filled)

class MockApplicationAdapter:
    def __init__(self, browser: ApplicationBrowser):
        self.browser = browser
        
    async def prepare_draft(self, application_id: str, job_id: str, profile: Profile, apply_url: str) -> Optional[ApplicationDraft]:
        logger.info(f"MockATS: Inspecting form for {apply_url}")
        
        inspection = await self.browser.inspect_form(apply_url)
        if not inspection.get("success"):
            logger.error(f"Failed to inspect form: {inspection.get('reason')}")
            return None
            
        form_fields = inspection.get("fields", [])
        mapped_fields = ProfileFieldMapper.map_fields(profile, form_fields)
        
        unanswered = [
            f.field_id for f in mapped_fields 
            if f.required and f.source == FieldSource.REQUIRES_USER_INPUT
        ]
        
        draft = ApplicationDraft(
            application_id=application_id,
            job_id=job_id,
            destination=apply_url,
            fields=mapped_fields,
            unanswered_required_fields=unanswered,
            resume_reference=profile.resume_path,
            ready_for_submission=len(unanswered) == 0
        )
        return draft
        
    async def submit_draft(self, apply_url: str, fields: List[ApplicationField]) -> Dict[str, Any]:
        filled = [
            {
                "id": f.field_id,
                "label": f.label,
                "type": f.type,
                "value": f.value
            }
            for f in fields
        ]
        return await self.browser.submit_form(apply_url, filled)

class ApplicationRegistry:
    def __init__(self, browser: ApplicationBrowser):
        self.browser = browser
        self.adapters = {
            "greenhouse": GreenhouseApplicationAdapter(self.browser),
            "mock": MockApplicationAdapter(self.browser)
        }
        
    def get_adapter(self, url: str):
        if "boards.greenhouse.io" in url or "boards-api.greenhouse.io" in url or "greenhouse.io" in url:
            return self.adapters["greenhouse"]
        if "localhost" in url or "127.0.0.1" in url or "mock" in url:
            return self.adapters["mock"]
            
        return None
