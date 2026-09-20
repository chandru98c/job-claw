import yaml
import os
import sys
import asyncio
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, '..'))
load_dotenv(os.path.join(script_dir, '..', '.env'))

from app.database.database import SessionLocal
from app.database.models import Source

def sync_registry():
    yaml_path = os.path.join(script_dir, '..', 'config', 'registry.yaml')
    with open(yaml_path, 'r') as f:
        registry = yaml.safe_load(f)

    inserted = 0
    updated = 0

    with SessionLocal() as session:
        for ats_group, sources in registry.items():
            for s_data in sources:
                source_id = s_data['source_id']
                source = session.query(Source).filter_by(id=source_id).first()

                if source:
                    # Update
                    source.domain = s_data['domain']
                    source.start_url = s_data['careers_url']
                    source.ats_type = s_data['ats_type']
                    source.is_active = s_data['enabled']
                    updated += 1
                else:
                    # Insert
                    new_source = Source(
                        id=source_id,
                        domain=s_data['domain'],
                        start_url=s_data['careers_url'],
                        ats_type=s_data['ats_type'],
                        is_active=s_data['enabled'],
                    )
                    session.add(new_source)
                    inserted += 1
        
        session.commit()
    
    print(f"Sync complete. Inserted: {inserted}, Updated: {updated}")

if __name__ == '__main__':
    sync_registry()
