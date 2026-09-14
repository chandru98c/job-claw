from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class NetworkCandidate(BaseModel):
    """Metadata collected from network observation during browser fallback."""
    method: str
    url: str
    status: Optional[int] = None
    content_type: Optional[str] = None
    resource_type: Optional[str] = None


class AcquisitionResult(BaseModel):
    """Bounded response from any acquisition strategy."""
    success: bool
    method: str  # e.g., "HTTP", "BROWSER"
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    bounded_content: Optional[bytes] = None
    network_candidates: List[NetworkCandidate] = Field(default_factory=list)
    reason: Optional[str] = None


class AcquisitionStrategy(ABC):
    """
    Base interface for secure job data acquisition.
    Implementations (HTTP, Browser) must adhere strictly to resource and security policies.
    """

    @abstractmethod
    async def acquire(self, url: str) -> AcquisitionResult:
        """
        Attempt to acquire content from the specified URL safely.
        """
        pass
