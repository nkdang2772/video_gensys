"""Add visual-first reference metadata and provisional shot timing.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("reference") as batch_op:
        batch_op.add_column(sa.Column("generation_prompt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aliases_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("shot") as batch_op:
        batch_op.add_column(sa.Column("planned_duration_sec", sa.Float(), nullable=True))
        batch_op.create_check_constraint(
            "ck_shot_planned_duration", "planned_duration_sec IS NULL OR planned_duration_sec > 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("shot") as batch_op:
        batch_op.drop_constraint("ck_shot_planned_duration", type_="check")
        batch_op.drop_column("planned_duration_sec")
    with op.batch_alter_table("reference") as batch_op:
        batch_op.drop_column("aliases_json")
        batch_op.drop_column("generation_prompt")
