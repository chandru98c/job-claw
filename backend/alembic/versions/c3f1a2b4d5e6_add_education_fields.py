"""Add education_level to jobs and education to profiles

Revision ID: c3f1a2b4d5e6
Revises: 1186d44d4283
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3f1a2b4d5e6'
down_revision: Union[str, None] = 'f8d49a2820e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('education_level', sa.String(), nullable=True))
    op.create_index('ix_jobs_education_level', 'jobs', ['education_level'], unique=False)
    op.add_column('profiles', sa.Column('education', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('profiles', 'education')
    op.drop_index('ix_jobs_education_level', table_name='jobs')
    op.drop_column('jobs', 'education_level')
