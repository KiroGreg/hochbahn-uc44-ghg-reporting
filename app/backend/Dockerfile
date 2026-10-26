# Build context: project root (one level above app/).
# `Use Case/` and `app/` both need to be in the build context because
# the backend code imports from `Use Case/models/` and reads the source
# Excel files from `Use Case/`.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work

COPY app/backend/requirements.txt /work/app/backend/requirements.txt
RUN pip install --no-cache-dir -r /work/app/backend/requirements.txt

COPY app/backend /work/app/backend
COPY ["Use Case", "/work/Use Case"]

WORKDIR /work/app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
