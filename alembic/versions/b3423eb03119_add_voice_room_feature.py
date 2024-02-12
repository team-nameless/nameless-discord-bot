"""Add voice room feature

Revision ID: b3423eb03119
Revises: 629190f29858
Create Date: 2024-01-21 11:15:51.336849

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3423eb03119'
down_revision = '629190f29858'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("Guilds", sa.Column("VoiceRoomChannelId", sa.Interval(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("Guilds", "VoiceRoomChannelId")
    # ### end Alembic commands ###