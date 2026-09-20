import yaml
import sys
import os

def validate_registry(filepath: str):
    with open(filepath, 'r') as f:
        registry = yaml.safe_load(f)

    if not registry:
        print("Error: Registry is empty")
        sys.exit(1)

    seen_ids = set()
    errors = []

    for ats_group, sources in registry.items():
        if not isinstance(sources, list):
            errors.append(f"Group '{ats_group}' is not a list")
            continue

        for i, source in enumerate(sources):
            # Check required fields
            required_fields = ['source_id', 'company', 'domain', 'careers_url', 'source_type', 'ats_type', 'identifier', 'enabled']
            for field in required_fields:
                if field not in source:
                    errors.append(f"Source at index {i} in group '{ats_group}' missing required field: {field}")

            # Check for duplicate IDs
            source_id = source.get('source_id')
            if source_id:
                if source_id in seen_ids:
                    errors.append(f"Duplicate source_id found: {source_id}")
                seen_ids.add(source_id)

    if errors:
        print(f"Validation failed with {len(errors)} errors:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)
    
    print(f"Registry is valid. Checked {len(seen_ids)} unique sources.")

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    validate_registry(os.path.join(script_dir, '..', 'config', 'registry.yaml'))
