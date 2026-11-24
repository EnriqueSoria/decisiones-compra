FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ARG COMPRA_UID=1000
ARG COMPRA_GID=1000

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && chown "${COMPRA_UID}:${COMPRA_GID}" /app

COPY build.py local_cache.py source_metadata.py serve.py ./
COPY templates/ templates/
COPY static/ static/
COPY datos/ datos/
COPY --chown=${COMPRA_UID}:${COMPRA_GID} cache/ cache/

USER ${COMPRA_UID}:${COMPRA_GID}
EXPOSE 8000
CMD ["python", "serve.py"]

FROM runtime AS generated
RUN python build.py
