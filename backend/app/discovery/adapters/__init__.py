# app.discovery.adapters — ATS adapter implementations
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .ashby import AshbyAdapter
from .workable import WorkableAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .workday import WorkdayAdapter
from .zohorecruit import ZohoRecruitAdapter
from .naukri import NaukriAdapter
from .recruitee import RecruiteeAdapter
from .breezy import BreezyAdapter
from .teamtailor import TeamtailorAdapter
from .personio import PersonioAdapter
from .bamboohr import BambooHRAdapter
from .keka import KekaAdapter
from .darwinbox import DarwinboxAdapter
from .wordpress import WordPressAdapter

__all__ = [
    "GreenhouseAdapter",
    "LeverAdapter",
    "AshbyAdapter",
    "WorkableAdapter",
    "SmartRecruitersAdapter",
    "WorkdayAdapter",
    "ZohoRecruitAdapter",
    "NaukriAdapter",
    "RecruiteeAdapter",
    "BreezyAdapter",
    "TeamtailorAdapter",
    "PersonioAdapter",
    "BambooHRAdapter",
    "KekaAdapter",
    "DarwinboxAdapter",
    "WordPressAdapter",
]
