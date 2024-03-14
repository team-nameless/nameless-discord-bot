"""Add mute_timeout_interval

Revision ID: 629190f29858
Revises: 7075bbb95141
Create Date: 2023-04-05 10:19:35.209509

"""
import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision = "629190f29858"
down_revision = "7075bbb95141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Guilds", sa.Column("MuteTimeoutInterval", sa.Interval(), nullable=True))


def downgrade() -> None:
    op.drop_column("Guilds", "MuteTimeoutInterval")
