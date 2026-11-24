"""Keep previously synced offer associations in the archive on cancel."""
from alembic import op
import sqlalchemy as sa


revision = "0002_offer_archive"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offer_bindings",
        sa.Column("ever_synced", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection = op.get_bind()
    bindings = connection.execute(sa.text(
        "SELECT id, campaign_id, stream_id, offer_id, baseline_present, present "
        "FROM offer_bindings"
    )).mappings()
    for binding in bindings:
        was_synced = binding["baseline_present"] or not binding["present"]
        if not was_synced:
            restore = connection.execute(sa.text(
                "SELECT 1 FROM operation_logs "
                "WHERE campaign_id = :campaign_id AND stream_id = :stream_id "
                "AND action = 'offer.restore.draft' "
                "AND details LIKE :details LIMIT 1"
            ), {
                "campaign_id": binding["campaign_id"],
                "stream_id": binding["stream_id"],
                "details": f"%Оффер {binding['offer_id']} возвращён в черновик%",
            }).first()
            was_synced = restore is not None
        if was_synced:
            connection.execute(sa.text(
                "UPDATE offer_bindings SET ever_synced = TRUE WHERE id = :id"
            ), {"id": binding["id"]})

    op.alter_column("offer_bindings", "ever_synced", server_default=None)


def downgrade() -> None:
    op.drop_column("offer_bindings", "ever_synced")
