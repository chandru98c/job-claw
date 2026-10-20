import yaml
import os
import sys
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, '..'))
load_dotenv(os.path.join(script_dir, '..', '.env'))

from app.database.database import SessionLocal
from app.database.models import Source

def sync_registry():
    yaml_path = os.path.join(script_dir, '..', 'config', 'registry.yaml')
    with open(yaml_path, 'r', encoding='utf-8') as f:
        registry = yaml.safe_load(f)

    inserted = 0
    updated = 0

    with SessionLocal() as session:
        # Load all existing sources in one single bulk query for instant O(1) comparison
        existing_sources = {s.id: s for s in session.query(Source).all()}

        new_objects = []
        for ats_group, sources in registry.items():
            if not isinstance(sources, list):
                continue
            for s_data in sources:
                source_id = s_data.get('source_id')
                if not source_id:
                    continue

                if source_id in existing_sources:
                    source = existing_sources[source_id]
                    changed = False
                    new_domain = s_data.get('domain', '')
                    new_url = s_data.get('careers_url', '')
                    new_ats = s_data.get('ats_type', '')
                    new_active = s_data.get('enabled', True)

                    if source.domain != new_domain:
                        source.domain = new_domain
                        changed = True
                    if source.start_url != new_url:
                        source.start_url = new_url
                        changed = True
                    if source.ats_type != new_ats:
                        source.ats_type = new_ats
                        changed = True
                    if source.is_active != new_active:
                        source.is_active = new_active
                        changed = True

                    if changed:
                        updated += 1
                else:
                    # Queue new record for fast batch insert
                    new_source = Source(
                        id=source_id,
                        domain=s_data.get('domain', ''),
                        start_url=s_data.get('careers_url', ''),
                        ats_type=s_data.get('ats_type', ''),
                        is_active=s_data.get('enabled', True),
                    )
                    new_objects.append(new_source)
                    inserted += 1

                # Flush new objects in batches of 1,000
                if len(new_objects) >= 1000:
                    session.add_all(new_objects)
                    session.commit()
                    new_objects = []
                    print(f"Flushed batch... total inserted so far: {inserted}")

        if new_objects:
            session.add_all(new_objects)
            session.commit()
        if updated > 0:
            session.commit()

        print(f"Sync complete! Inserted: {inserted}, Updated: {updated}")

if __name__ == '__main__':
    sync_registry()
