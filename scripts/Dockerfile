FROM python:3.11-slim
WORKDIR /project
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY scripts/ /project/scripts/
ENV PYTHONUNBUFFERED=1
CMD ["python", "scripts/generate_synthetic_batch.py", "--output", "/project/data/synthetic"]
