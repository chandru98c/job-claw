from typing import List, Dict, Any, Tuple
from app.database.models import Profile
from app.schemas.application import ApplicationField, FieldSource

class ProfileFieldMapper:
    """
    Deterministically maps explicitly provided Profile data to application fields.
    Does NOT hallucinate missing information.
    """
    
    @staticmethod
    def map_fields(profile: Profile, form_fields: List[Dict[str, Any]]) -> List[ApplicationField]:
        mapped = []
        
        # Simple rule-based deterministic mapping
        for f in form_fields:
            field_id = f.get("id", "")
            label = f.get("label", "").lower()
            f_type = f.get("type", "text")
            required = f.get("required", False)
            options = f.get("options", None)
            
            app_field = ApplicationField(
                field_id=field_id,
                label=f.get("label", ""),
                type=f_type,
                required=required,
                options=options,
                placeholder=f.get("placeholder")
            )
            
            # Simple keyword heuristic mapping - STRICTLY BOUNDED to explicit profile fields
            if "first name" in label:
                app_field.value = profile.name.split(" ")[0] if profile.name else None
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "last name" in label:
                parts = profile.name.split(" ") if profile.name else []
                app_field.value = " ".join(parts[1:]) if len(parts) > 1 else None
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "name" in label and not ("company" in label):
                app_field.value = profile.name
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "email" in label:
                app_field.value = profile.email
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "phone" in label:
                app_field.value = profile.phone
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "location" in label or "city" in label:
                app_field.value = profile.location
                app_field.source = FieldSource.PROFILE if app_field.value else FieldSource.REQUIRES_USER_INPUT
            elif "resume" in label or "cv" in label or (f_type == "file" and ("resume" in label or "cv" in label)):
                if profile.resume_path:
                    app_field.value = profile.resume_path
                    app_field.source = FieldSource.PROFILE
                else:
                    app_field.source = FieldSource.REQUIRES_USER_INPUT
            elif any(q in label for q in ["why", "tell us", "describe", "experience", "salary", "visa", "sponsorship", "authorization", "gender", "race", "disability", "veteran", "criminal"]):
                # Explicitly block sensitive / complex questions
                app_field.source = FieldSource.REQUIRES_USER_INPUT
            else:
                app_field.source = FieldSource.UNMAPPED if not required else FieldSource.REQUIRES_USER_INPUT
                
            mapped.append(app_field)
            
        return mapped
