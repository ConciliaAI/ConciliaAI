# Concilia AI em um contêiner: monta o front (React) e roda a API (FastAPI), que serve as telas.
# Uso no servidor: veja deploy/LEIA-ME.md.

FROM node:22-slim AS front
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CONCILIA_DADOS=/dados
# O OCR (RapidOCR) usa o OpenCV, que precisa destas bibliotecas do sistema.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ app/
COPY web/ web/
COPY scripts/ scripts/
COPY ferramentas/ ferramentas/
COPY docs/ docs/
COPY --from=front /front/dist frontend/dist
VOLUME ["/dados"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
