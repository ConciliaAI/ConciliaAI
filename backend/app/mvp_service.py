from app.status_sync import sync_batch
"""Persistência e reaplicação segura do pipeline do MVP Essencial."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.intelligence import segment, extract_fields, reconcile
from app.models import DocumentGroup, Finding, Page, SourceFile, ReviewAction

REVIEW_THRESHOLD = .75


def pages_for_group(db: Session, group: DocumentGroup):
    return [{"number": pg.page_number, "text": pg.ocr_text, "confidence": pg.ocr_confidence or 0}
            for pg in db.scalars(select(Page).where(Page.source_file_id == group.source_file_id,
                Page.page_number >= group.start_page, Page.page_number <= group.end_page).order_by(Page.page_number))]


def build_groups(db: Session, batch_id: int):
    sync_batch(db, batch_id)
    files = list(db.scalars(select(SourceFile).where(SourceFile.batch_id == batch_id).order_by(SourceFile.id)))
    if not files:
        raise ValueError("Lote sem arquivos")
    # Prevenção de apagar correções humanas ou registros de auditoria em nova análise.
    existing = list(db.scalars(select(DocumentGroup).join(SourceFile).where(SourceFile.batch_id == batch_id)))
    if existing:
        raise ValueError("Lote já analisado: os agrupamentos foram preservados para revisão")
    if any(f.status not in ("completed", "error") for f in files):
        raise ValueError("Aguarde a conclusão do OCR antes de analisar")
    for f in files:
        pages = list(db.scalars(select(Page).where(Page.source_file_id == f.id).order_by(Page.page_number)))
        if any(p.status != "ok" for p in pages):
            raise ValueError("O OCR de algumas páginas falhou; corrija antes de segmentar")
        payload = [{"number": p.page_number, "text": p.ocr_text, "confidence": p.ocr_confidence} for p in pages]
        for g in segment(payload):
            gp = [p for p in payload if g.start <= p["number"] <= g.end]
            db.add(DocumentGroup(source_file_id=f.id, start_page=g.start, end_page=g.end,
                                 document_type=g.kind, confidence=g.confidence, reasons=g.reasons,
                                 fields=extract_fields(gp, g.kind),
                                 review_status="pendente" if g.confidence < REVIEW_THRESHOLD or g.kind == "outros" else "auto_classificado"))
    db.flush()
    recompute_findings(db, batch_id)
    db.commit()


def recompute_findings(db: Session, batch_id: int):
    """Reconciliações resolvidas não são sobrescritas silenciosamente."""
    old = list(db.scalars(select(Finding).where(Finding.batch_id == batch_id)))
    if any(f.status in ("aceita", "rejeitada") for f in old):
        raise ValueError("Existem divergências revisadas; não é possível recalcular sem preservação de histórico")
    db.execute(delete(Finding).where(Finding.batch_id == batch_id))
    groups = list(db.scalars(select(DocumentGroup).join(SourceFile).where(SourceFile.batch_id == batch_id)))
    records = [{"id": g.id, "kind": g.document_type, "fields": g.fields or {}} for g in groups]
    for finding in reconcile(records):
        db.add(Finding(batch_id=batch_id, **finding))
    db.flush()


def audit(db: Session, group: DocumentGroup, reviewer_id: int, action: str, before: dict, note: str):
    db.add(ReviewAction(document_id=group.id, reviewer_id=reviewer_id, action=action,
                        before=before, after={"start_page": group.start_page, "end_page": group.end_page,
                                              "document_type": group.document_type, "review_status": group.review_status},
                        justification=note))

