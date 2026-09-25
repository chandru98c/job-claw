import pytest
from sqlalchemy.orm import Session
from app.database.models import Job, JobSourceProvenance, Source
from app.schemas.discovery import RawJob, DiscoveryProvenanceDTO
from app.canonicalization.identity import resolve_identity
from app.canonicalization.normalize import normalize_title, normalize_company
from app.database.database import SessionLocal
from datetime import datetime, timezone
import uuid

def create_raw_job(title, company, source_id, source_job_id, apply_url=None):
    return RawJob(
        title=title,
        company=company,
        description="Desc",
        location="San Francisco",
        employment_type="Full-time",
        remote_status="On-site",
        discovered_at=datetime.now(timezone.utc),
        provenance=DiscoveryProvenanceDTO(
            strategy_id="test",
            source_id=source_id,
            source_type="direct_ats",
            source_job_id=source_job_id,
            source_url="https://test.com",
            apply_url=apply_url,
            discovery_method="test"
        ),
        provider_metadata={}
    )

def test_same_source_same_source_job_id():
    sync_db_session = SessionLocal()
    try:
        source_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        unique_title = f"engineer {uuid.uuid4()}"
        unique_company = f"acme {uuid.uuid4()}"
        
        source = Source(id=source_id, domain=str(uuid.uuid4()), start_url="https://test.com", ats_type="custom")
        sync_db_session.add(source)
        job = Job(id=job_id, title=normalize_title(unique_title), company_name=normalize_company(unique_company), canonical_apply_url="https://test.com")
        prov = JobSourceProvenance(job_id=job_id, source_id=source_id, source_job_id="123", source_url="https://test.com", source_type="test")
        sync_db_session.add(job)
        sync_db_session.add(prov)
        sync_db_session.commit()
        
        raw_job = create_raw_job(unique_title, unique_company, source_id, "123")
        match = resolve_identity(sync_db_session, raw_job)
        assert match is not None
        assert match.id == job_id
    finally:
        sync_db_session.close()

def test_same_source_different_source_job_id():
    sync_db_session = SessionLocal()
    try:
        source_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        unique_title = f"engineer {uuid.uuid4()}"
        unique_company = f"acme {uuid.uuid4()}"
        
        source = Source(id=source_id, domain=str(uuid.uuid4()), start_url="https://test.com", ats_type="custom")
        sync_db_session.add(source)
        job = Job(id=job_id, title=normalize_title(unique_title), company_name=normalize_company(unique_company), canonical_apply_url="https://test.com")
        prov = JobSourceProvenance(job_id=job_id, source_id=source_id, source_job_id="123", source_url="https://test.com", source_type="test")
        sync_db_session.add(job)
        sync_db_session.add(prov)
        sync_db_session.commit()
        
        raw_job = create_raw_job(unique_title, unique_company, source_id, "456")
        match = resolve_identity(sync_db_session, raw_job)
        assert match is None
    finally:
        sync_db_session.close()

def test_different_source_same_source_job_id():
    sync_db_session = SessionLocal()
    try:
        source_id_1 = str(uuid.uuid4())
        source_id_2 = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        unique_title = f"engineer {uuid.uuid4()}"
        unique_company = f"acme {uuid.uuid4()}"
        
        source1 = Source(id=source_id_1, domain=str(uuid.uuid4()), start_url="https://test1.com", ats_type="custom")
        source2 = Source(id=source_id_2, domain=str(uuid.uuid4()), start_url="https://test2.com", ats_type="custom")
        sync_db_session.add(source1)
        sync_db_session.add(source2)
        job = Job(id=job_id, title=normalize_title(unique_title), company_name=normalize_company(unique_company), canonical_apply_url="https://test.com")
        prov = JobSourceProvenance(job_id=job_id, source_id=source_id_1, source_job_id="123", source_url="https://test.com", source_type="test")
        sync_db_session.add(job)
        sync_db_session.add(prov)
        sync_db_session.commit()
        
        raw_job = create_raw_job(unique_title, unique_company, source_id_2, "123")
        match = resolve_identity(sync_db_session, raw_job)
        assert match is not None
        assert match.id == job_id
    finally:
        sync_db_session.close()

def test_same_title_company_different_ids():
    sync_db_session = SessionLocal()
    try:
        source_id_1 = str(uuid.uuid4())
        source_id_2 = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        unique_title = f"engineer {uuid.uuid4()}"
        unique_company = f"acme {uuid.uuid4()}"
        
        source1 = Source(id=source_id_1, domain=str(uuid.uuid4()), start_url="https://test1.com", ats_type="custom")
        source2 = Source(id=source_id_2, domain=str(uuid.uuid4()), start_url="https://test2.com", ats_type="custom")
        sync_db_session.add(source1)
        sync_db_session.add(source2)
        job = Job(id=job_id, title=normalize_title(unique_title), company_name=normalize_company(unique_company), canonical_apply_url="https://test.com")
        prov = JobSourceProvenance(job_id=job_id, source_id=source_id_1, source_job_id="123", source_url="https://test.com", source_type="test")
        sync_db_session.add(job)
        sync_db_session.add(prov)
        sync_db_session.commit()
        
        raw_job = create_raw_job(unique_title, unique_company, source_id_2, "456")
        match = resolve_identity(sync_db_session, raw_job)
        assert match is not None
        assert match.id == job_id
    finally:
        sync_db_session.close()

def test_missing_source_id_cannot_masquerade():
    sync_db_session = SessionLocal()
    try:
        job_id = str(uuid.uuid4())
        unique_title = f"engineer {uuid.uuid4()}"
        unique_company = f"acme {uuid.uuid4()}"
        
        job = Job(id=job_id, title=normalize_title(unique_title), company_name=normalize_company(unique_company), canonical_apply_url="https://test.com")
        prov = JobSourceProvenance(job_id=job_id, source_id=None, source_job_id="123", source_url="https://test.com", source_type="test")
        sync_db_session.add(job)
        sync_db_session.add(prov)
        sync_db_session.commit()
        
        raw_job = create_raw_job(unique_title, unique_company, None, "456")
        match = resolve_identity(sync_db_session, raw_job)
        assert match is not None
        assert match.id == job_id
    finally:
        sync_db_session.close()
