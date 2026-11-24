"""Initial local editor state and operation history."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_streams",
        sa.Column("stream_id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("managed_offer_flow", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaign_streams_campaign_id", "campaign_streams", ["campaign_id"])

    op.create_table(
        "offer_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("stream_name", sa.String(length=255), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("offer_name", sa.String(length=512), nullable=False),
        sa.Column("baseline_present", sa.Boolean(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("baseline_share", sa.Integer(), nullable=False),
        sa.Column("share", sa.Integer(), nullable=False),
        sa.Column("baseline_pinned", sa.Boolean(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),
    )
    op.create_index("ix_offer_bindings_campaign_id", "offer_bindings", ["campaign_id"])
    op.create_index("ix_offer_bindings_stream_id", "offer_bindings", ["stream_id"])
    op.create_index("ix_offer_bindings_offer_id", "offer_bindings", ["offer_id"])

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=True),
        sa.Column("stream_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operation_logs_campaign_id", "operation_logs", ["campaign_id"])
    op.create_index("ix_operation_logs_stream_id", "operation_logs", ["stream_id"])
    op.create_index("ix_operation_logs_created_at", "operation_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_operation_logs_created_at", table_name="operation_logs")
    op.drop_index("ix_operation_logs_stream_id", table_name="operation_logs")
    op.drop_index("ix_operation_logs_campaign_id", table_name="operation_logs")
    op.drop_table("operation_logs")
    op.drop_index("ix_offer_bindings_offer_id", table_name="offer_bindings")
    op.drop_index("ix_offer_bindings_stream_id", table_name="offer_bindings")
    op.drop_index("ix_offer_bindings_campaign_id", table_name="offer_bindings")
    op.drop_table("offer_bindings")
    op.drop_index("ix_campaign_streams_campaign_id", table_name="campaign_streams")
    op.drop_table("campaign_streams")
