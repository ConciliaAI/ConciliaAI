from sqlalchemy import select

from app.models import Batch, Page, SourceFile


def sync_batch(db, batch_id: int):
    """Reconcilia os estados persistidos com os resultados reais do OCR."""
    batch = db.get(Batch, batch_id)
    if batch is None:
        return None

    files = list(
        db.scalars(
            select(SourceFile)
            .where(SourceFile.batch_id == batch_id)
            .order_by(SourceFile.id)
        )
    )

    for file in files:
        states = list(
            db.scalars(
                select(Page.status).where(Page.source_file_id == file.id)
            )
        )

        if not states:
            continue

        if all(state == "ok" for state in states):
            file.status = "completed"
        elif all(state in ("ok", "error") for state in states):
            file.status = "error"
        elif any(state in ("processing", "ok", "error") for state in states):
            file.status = "processing"
        else:
            file.status = "pending"

    file_states = [file.status for file in files]

    if file_states and all(state == "completed" for state in file_states):
        batch.status = "completed"
    elif file_states and all(
        state in ("completed", "error") for state in file_states
    ):
        batch.status = "error"
    elif any(
        state in ("processing", "completed", "error")
        for state in file_states
    ):
        batch.status = "processing"

    db.commit()
    return batch.status
