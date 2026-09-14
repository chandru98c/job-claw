import os
from typing import Tuple

if os.getenv("E2E_MODE") == "1":
    from app.core.security import UrlValidator
    original_validate = UrlValidator.validate_and_resolve
    
    @classmethod
    def e2e_validate(cls, url: str) -> Tuple[str, str]:
        if url.startswith("http://127.0.0.1:8000/mock-ats/job/"):
            # Explicitly allow the local mock ATS for E2E tests ONLY
            return url, "127.0.0.1"
        # Delegate everything else to the strict production validation
        return original_validate.__func__(cls, url)

    UrlValidator.validate_and_resolve = e2e_validate

# Now import the production worker settings
from app.workers.settings import WorkerSettings
