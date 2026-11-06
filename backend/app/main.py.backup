from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, make_token, password_hasher
from app.config import get_settings
from app.database import get_db
from app.document_processing import ALLOWED_TYPES, count_pages
from app.models import Batch, Page, SourceFile, User
from app.storage import ensure_bucket, upload_stream
from app.tasks import process_page

MAX_FILE_BYTES = 40 * 1024 * 1024  # Limite MVP; upload multipart direto ao S3: fase futura.
MAX_PAGES = 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket()
    yield


app = FastAPI(title="Concilia AI", version="0.7.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=[part.strip() for part in get_settings().cors_origins.split(",")],
    allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"])


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    total_documents: int


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    page_number: int
    status: str
    ocr_confidence: float | None
    ocr_method: str | None
    ocr_text: str | None
    word_boxes: list | None
    error: str | None


class FileOut(BaseModel):
    id: int
    filename: str
    status: str
    total_pages: int
    completed_pages: int
    error_pages: int


def owned_batch(batch_id: int, user: User, db: Session) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None or (user.role != "admin" and batch.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    return batch


@app.get("/health")
def health():
    return {"status": "ok", "phase": "mvp-essential"}


@app.post("/auth/token")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if user is None or not password_hasher.verify(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return {"access_token": make_token(user.username), "token_type": "bearer", "role": user.role}


@app.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "role": user.role}


@app.post("/batches", response_model=BatchOut, status_code=201)
def create_batch(user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = Batch(owner_id=user.id, status="created", total_documents=0)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@app.get("/batches", response_model=list[BatchOut])
def list_batches(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Batch).order_by(Batch.id.desc())
    if user.role != "admin":
        stmt = stmt.where(Batch.owner_id == user.id)
    return list(db.scalars(stmt))


@app.post("/batches/{batch_id}/upload", response_model=FileOut, status_code=201)
async def upload_document(batch_id: int, file: UploadFile = File(...),
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    batch = owned_batch(batch_id, user, db)
    if batch.status == "processing":
        raise HTTPException(409, "Aguarde o lote terminar antes de enviar mais arquivos")
    filename = Path(file.filename or "").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise HTTPException(415, "Aceitos: PDF, PNG, JPEG e TIFF. XML/ZIP serão integrados em outra etapa")
    # Limite em memória para MVP, com checagem durante leitura.
    pieces = bytearray()
    while chunk := await file.read(1024 * 1024):
        pieces.extend(chunk)
        if len(pieces) > MAX_FILE_BYTES:
            raise HTTPException(413, "Arquivo acima do limite de 40 MB do MVP")
    raw = bytes(pieces)
    if not raw:
        raise HTTPException(400, "Arquivo vazio")
    try:
        n = count_pages(raw, ext)
    except Exception as exc:
        raise HTTPException(422, f"Arquivo ilegível ou inválido: {exc}") from exc
    if not 1 <= n <= MAX_PAGES:
        raise HTTPException(422, "Arquivo sem páginas ou com mais de 500 páginas")
    object_key = f"batches/{batch_id}/{uuid4().hex}{ext}"
    try:
        upload_stream(object_key, BytesIO(raw), ALLOWED_TYPES[ext])
    except Exception as exc:
        raise HTTPException(503, "Falha no armazenamento do arquivo") from exc
    source = SourceFile(batch_id=batch_id, filename=filename[:255],
        content_type=ALLOWED_TYPES[ext], object_key=object_key, sha256=sha256(raw).hexdigest(),
        size_bytes=len(raw), total_pages=n, status="uploaded")
    db.add(source)
    db.flush()
    db.add_all([Page(source_file_id=source.id, page_number=i, status="pending")
                for i in range(1, n + 1)])
    batch.total_documents += 1  # Total de arquivos de origem; a separação é da Fase 4.
    batch.status = "uploaded"
    db.commit()
    return FileOut(id=source.id, filename=source.filename, status=source.status,
                   total_pages=n, completed_pages=0, error_pages=0)


@app.post("/batches/{batch_id}/start")
def start_batch(batch_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    batch = owned_batch(batch_id, user, db)
    pages = list(db.scalars(select(Page).join(SourceFile).where(
        SourceFile.batch_id == batch_id, Page.status == "pending")))
    if not pages:
        raise HTTPException(409, "Não há páginas pendentes; envie um arquivo ou consulte o progresso")
    batch.status = "processing"
    db.commit()
    try:
        for page in pages:
            process_page.delay(page.id)
    except Exception as exc:
        # As tarefas já entregues continuam válidas. Uma nova chamada reenfileira
        # somente as páginas ainda pendentes. Não marcamos lotes como concluídos.
        raise HTTPException(503, "Fila indisponível; tente iniciar novamente") from exc
    return {"batch_id": batch_id, "queued_pages": len(pages), "status": "processing"}


@app.get("/batches/{batch_id}/progress")
def progress(batch_id: int, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    batch = owned_batch(batch_id, user, db)
    files = list(db.scalars(select(SourceFile).where(SourceFile.batch_id == batch_id)
                            .order_by(SourceFile.id)))
    counters = {"pending": 0, "processing": 0, "ok": 0, "error": 0}
    output = []
    for f in files:
        states = list(db.scalars(select(Page.status).where(Page.source_file_id == f.id)))
        for s in states:
            counters[s] = counters.get(s, 0) + 1
        output.append(FileOut(id=f.id, filename=f.filename, status=f.status,
            total_pages=f.total_pages, completed_pages=states.count("ok"),
            error_pages=states.count("error")).model_dump())
    total = sum(counters.values())
    return {"batch_id": batch.id, "status": batch.status, "pages_total": total,
        "pages_done": counters["ok"] + counters["error"],
        "percent": round(100 * (counters["ok"] + counters["error"]) / total, 1) if total else 0,
        "counts": counters, "files": output}


@app.get("/batches/{batch_id}/pages", response_model=list[PageOut])
def list_pages(batch_id: int, include_boxes: bool = False, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    owned_batch(batch_id, user, db)
    records = list(db.scalars(select(Page).join(SourceFile).where(
        SourceFile.batch_id == batch_id).order_by(SourceFile.id, Page.page_number)))
    # Em lotes grandes, evita transferir coordenadas de cada palavra no polling do painel.
    return [PageOut.model_validate(p).model_copy(update={"word_boxes": None}) if not include_boxes
            else PageOut.model_validate(p) for p in records]


@app.get("/")
def index():
    return {"product": "Concilia AI", "message": "API MVP Essencial. Consulte /docs."}

# MVP Essencial: rotas adicionais sobre a API já existente.
from app.mvp_api import router as mvp_router
app.include_router(mvp_router)
