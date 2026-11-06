"""Endpoints MVP Essencial: autenticação herdada da Fase 3."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import current_user
from app.database import get_db
from app.models import Batch, SourceFile, DocumentGroup, Finding, Page, ReviewAction, User
from app.intelligence import DOC_TYPES, classify, extract_fields
from app.mvp_service import REVIEW_THRESHOLD, audit, build_groups, pages_for_group, recompute_findings

router = APIRouter(tags=["MVP Essencial"])


def own_batch(db, user, batch_id):
    batch = db.get(Batch, batch_id)
    if batch is None or (user.role != "admin" and batch.owner_id != user.id):
        raise HTTPException(404, "Lote não encontrado")
    return batch


def own_group(db, user, group_id):
    group = db.get(DocumentGroup, group_id)
    if group is None:
        raise HTTPException(404, "Documento não encontrado")
    source = db.get(SourceFile, group.source_file_id)
    own_batch(db, user, source.batch_id)
    return group, source.batch_id


def can_review(user):
    if user.role not in ("revisor", "admin"):
        raise HTTPException(403, "Apenas revisor/admin pode validar e corrigir documentos")


def doc_out(g):
    return {"id": g.id, "source_file_id": g.source_file_id,
            "start_page": g.start_page, "end_page": g.end_page,
            "document_type": g.document_type, "confidence": g.confidence,
            "reasons": g.reasons, "fields": g.fields, "review_status": g.review_status}


@router.post("/batches/{batch_id}/analyze")
def analyze(batch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_batch(db, user, batch_id)
    try:
        build_groups(db, batch_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    groups = list(db.scalars(select(DocumentGroup).join(SourceFile).where(SourceFile.batch_id == batch_id)))
    return {"batch_id": batch_id, "document_count": len(groups), "review_count": sum(g.review_status == "pendente" for g in groups)}


@router.get("/batches/{batch_id}/documents")
def documents(batch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_batch(db, user, batch_id)
    return [doc_out(g) for g in db.scalars(select(DocumentGroup).join(SourceFile).where(SourceFile.batch_id == batch_id).order_by(SourceFile.id, DocumentGroup.start_page))]


@router.get("/batches/{batch_id}/findings")
def findings(batch_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_batch(db, user, batch_id)
    return [{"id": f.id, "invoice_id": f.invoice_id, "contract_id": f.contract_id, "rule": f.rule,
             "severity": f.severity, "status": f.status, "message": f.message, "expected": f.expected,
             "observed": f.observed, "evidence": f.evidence, "resolution_note": f.resolution_note}
            for f in db.scalars(select(Finding).where(Finding.batch_id == batch_id).order_by(Finding.id))]


@router.get("/batches/{batch_id}/search")
def search(batch_id: int, q: str = Query(min_length=2, max_length=120), user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_batch(db, user, batch_id)
    # Busca simples no texto OCR; MVP limitado a 100 correspondências, sem índice FTS.
    pages = db.scalars(select(Page).join(SourceFile).where(SourceFile.batch_id == batch_id, Page.status == "ok"))
    results = []
    for p in pages:
        text = p.ocr_text or ""
        at = text.casefold().find(q.casefold())
        if at >= 0:
            results.append({"source_file_id": p.source_file_id, "page": p.page_number,
                            "excerpt": text[max(0, at - 80):at + len(q) + 100]})
            if len(results) == 100:
                break
    return results


class ReviewPayload(BaseModel):
    document_type: str | None = None
    approve: bool = False
    justification: str = Field(min_length=3, max_length=1000)


@router.patch("/documents/{document_id}/review")
def review(document_id: int, payload: ReviewPayload, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_review(user)
    g, batch_id = own_group(db, user, document_id)
    if payload.document_type and payload.document_type not in DOC_TYPES:
        raise HTTPException(422, "Tipo documental inválido")
    before = doc_out(g)
    if payload.document_type:
        g.document_type = payload.document_type
        g.fields = extract_fields(pages_for_group(db, g), g.document_type)
    g.review_status = "aprovado" if payload.approve else "corrigido"
    g.reviewed_by_id = user.id
    audit(db, g, user.id, "revisao", before, payload.justification)
    if payload.document_type and payload.document_type != before["document_type"]:
        try:
            recompute_findings(db, batch_id)
        except ValueError as exc:
            db.rollback()
            raise HTTPException(409, str(exc)) from exc
    db.commit()
    return doc_out(g)


class SplitPayload(BaseModel):
    next_start_page: int
    justification: str = Field(min_length=3, max_length=1000)


@router.post("/documents/{document_id}/split")
def split(document_id: int, payload: SplitPayload, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_review(user)
    g, batch_id = own_group(db, user, document_id)
    if not g.start_page < payload.next_start_page <= g.end_page:
        raise HTTPException(422, "Página de divisão fora do documento")
    before = doc_out(g)
    end = g.end_page
    g.end_page = payload.next_start_page - 1
    first_pages = pages_for_group(db, g)
    kind, conf, reasons = classify("\n".join(p.get("text") or "" for p in first_pages[:2]))
    g.document_type = kind
    g.confidence = min(conf, min(float(p["confidence"]) for p in first_pages))
    g.fields = extract_fields(first_pages, kind)
    g.review_status = "corrigido"
    new = DocumentGroup(source_file_id=g.source_file_id, start_page=payload.next_start_page, end_page=end,
                        document_type="outros", confidence=0, reasons=["Divisão manual"], fields={}, review_status="pendente")
    db.add(new)
    db.flush()
    rest = pages_for_group(db, new)
    kind, conf, reasons = classify("\n".join(p.get("text") or "" for p in rest[:2]))
    new.document_type = kind
    new.confidence = min(conf, min(float(p["confidence"]) for p in rest))
    new.reasons = reasons + ["Divisão manual"]
    new.fields = extract_fields(rest, kind)
    audit(db, g, user.id, "dividir", before, payload.justification)
    try:
        recompute_findings(db, batch_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {"first": doc_out(g), "second": doc_out(new)}


class MergePayload(BaseModel):
    other_document_id: int
    justification: str = Field(min_length=3, max_length=1000)


@router.post("/documents/{document_id}/merge")
def merge(document_id: int, payload: MergePayload, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_review(user)
    g, batch_id = own_group(db, user, document_id)
    other, other_batch = own_group(db, user, payload.other_document_id)
    if g.id == other.id or batch_id != other_batch or g.source_file_id != other.source_file_id or g.end_page + 1 != other.start_page:
        raise HTTPException(422, "Escolha o documento imediatamente seguinte no mesmo arquivo")
    if db.scalar(select(ReviewAction).where(ReviewAction.document_id == other.id).limit(1)):
        raise HTTPException(409, "Documento seguinte tem histórico de revisão; junção bloqueada")
    before = doc_out(g)
    g.end_page = other.end_page
    group_pages = pages_for_group(db, g)
    g.document_type, conf, reasons = classify("\n".join(p.get("text") or "" for p in group_pages[:2]))
    g.confidence = min(conf, min(float(p["confidence"]) for p in group_pages))
    g.fields = extract_fields(group_pages, g.document_type)
    g.reasons = reasons + ["Junção manual"]
    g.review_status = "corrigido"
    # Exclui divergências antigas antes do documento referenciado para respeitar FKs.
    from sqlalchemy import delete
    existing = list(db.scalars(select(Finding).where(Finding.batch_id == batch_id)))
    if any(f.status in ("aceita", "rejeitada") for f in existing):
        db.rollback()
        raise HTTPException(409, "Existem divergências revisadas")
    db.execute(delete(Finding).where(Finding.batch_id == batch_id))
    db.delete(other)
    db.flush()
    audit(db, g, user.id, "juntar", before, payload.justification)
    recompute_findings(db, batch_id)
    db.commit()
    return doc_out(g)


class FindingResolution(BaseModel):
    decision: str
    justification: str = Field(min_length=3, max_length=1000)


@router.post("/findings/{finding_id}/resolve")
def resolve_finding(finding_id: int, payload: FindingResolution, user: User = Depends(current_user), db: Session = Depends(get_db)):
    can_review(user)
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Divergência não encontrada")
    own_batch(db, user, f.batch_id)
    if payload.decision not in ("aceita", "rejeitada"):
        raise HTTPException(422, "Decisão inválida")
    f.status = payload.decision
    f.resolution_note = f"{user.username}: {payload.justification}"
    db.commit()
    return {"id": f.id, "status": f.status}
