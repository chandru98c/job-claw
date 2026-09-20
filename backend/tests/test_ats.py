import pytest
from app.discovery.adapters.greenhouse import GreenhouseAdapter
from app.discovery.adapters.lever import LeverAdapter
from app.discovery.adapters.ashby import AshbyAdapter
from app.discovery.adapters.workable import WorkableAdapter
from app.discovery.adapters.smartrecruiters import SmartRecruitersAdapter

def test_greenhouse_recognition():
    adapter = GreenhouseAdapter()
    
    # Valid
    assert adapter.extract_board_identifier("https://boards.greenhouse.io/openai") == "openai"
    assert adapter.extract_board_identifier("https://boards-api.greenhouse.io/v1/boards/stripe/jobs") == "stripe"
    assert adapter.extract_board_identifier("https://airbnb.greenhouse.io") == "airbnb"
    
    # Invalid
    assert adapter.extract_board_identifier("https://www.google.com") is None
    assert adapter.extract_board_identifier("https://api.greenhouse.io") is None # reserved

def test_lever_recognition():
    adapter = LeverAdapter()
    
    assert adapter.extract_board_identifier("https://jobs.lever.co/netflix") == "netflix"
    assert adapter.extract_board_identifier("http://jobs.lever.co/spotify/1234") == "spotify"
    assert adapter.extract_board_identifier("https://lever.co/netflix") is None

def test_ashby_recognition():
    adapter = AshbyAdapter()
    
    assert adapter.extract_board_identifier("https://jobs.ashbyhq.com/reddit") == "reddit"
    assert adapter.extract_board_identifier("https://ashbyhq.com/reddit") is None

def test_workable_recognition():
    adapter = WorkableAdapter()
    
    assert adapter.extract_board_identifier("https://apply.workable.com/revolut") == "revolut"
    assert adapter.extract_board_identifier("https://workable.com/revolut") == "revolut"
    assert adapter.extract_board_identifier("https://apply.workable.com/api/v3/accounts/revolut/jobs") == "revolut"

def test_smartrecruiters_recognition():
    adapter = SmartRecruitersAdapter()
    
    assert adapter.extract_board_identifier("https://careers.smartrecruiters.com/Square") == "Square"
    assert adapter.extract_board_identifier("https://smartrecruiters.com/Square") == "Square"
