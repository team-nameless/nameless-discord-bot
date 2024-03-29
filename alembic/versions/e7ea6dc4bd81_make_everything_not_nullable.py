"""Make everything NOT NULLABLE

Revision ID: e7ea6dc4bd81
Revises: 25a6fd270c19
Create Date: 2024-03-14 19:05:03.532824

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7ea6dc4bd81'
down_revision = '25a6fd270c19'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Guilds', schema=None) as batch_op:
        batch_op.alter_column('IsWelcomeEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('IsGoodbyeEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('IsBotGreetingEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('IsDmPreferred',
               existing_type=sa.BOOLEAN(),
               nullable=False)
        batch_op.alter_column('WelcomeChannelId',
               existing_type=sa.BIGINT(),
               nullable=False)
        batch_op.alter_column('GoodbyeChannelId',
               existing_type=sa.BIGINT(),
               nullable=False)
        batch_op.alter_column('WelcomeMessage',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.alter_column('GoodbyeMessage',
               existing_type=sa.TEXT(),
               nullable=False)
        batch_op.alter_column('AudioRoleId',
               existing_type=sa.BIGINT(),
               nullable=False)
        batch_op.alter_column('VoiceRoomChannelId',
               existing_type=sa.BIGINT(),
               nullable=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('Guilds', schema=None) as batch_op:
        batch_op.alter_column('VoiceRoomChannelId',
               existing_type=sa.BIGINT(),
               nullable=True)
        batch_op.alter_column('AudioRoleId',
               existing_type=sa.BIGINT(),
               nullable=True)
        batch_op.alter_column('GoodbyeMessage',
               existing_type=sa.TEXT(),
               nullable=True)
        batch_op.alter_column('WelcomeMessage',
               existing_type=sa.TEXT(),
               nullable=True)
        batch_op.alter_column('GoodbyeChannelId',
               existing_type=sa.BIGINT(),
               nullable=True)
        batch_op.alter_column('WelcomeChannelId',
               existing_type=sa.BIGINT(),
               nullable=True)
        batch_op.alter_column('IsDmPreferred',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('IsBotGreetingEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('IsGoodbyeEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=True)
        batch_op.alter_column('IsWelcomeEnabled',
               existing_type=sa.BOOLEAN(),
               nullable=True)

    # ### end Alembic commands ###
