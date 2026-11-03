# Compatibility boundary: Alpine/musl avoids the clone3 seccomp incompatibility on the legacy
# CentOS 7 and Docker 19.03 Jenkins builder. Return to Debian slim after that builder is upgraded.
FROM python:3.13-alpine AS builder

ARG UV_VERSION=0.11.15
ARG PYPI_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=${PYPI_INDEX_URL} \
    UV_COMPILE_BYTECODE=1 \
    UV_CONCURRENT_DOWNLOADS=8 \
    UV_CONCURRENT_INSTALLS=4 \
    UV_DEFAULT_INDEX=${PYPI_INDEX_URL} \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1 \
    UV_PROJECT_ENVIRONMENT=/opt/parrot/venv

WORKDIR /build

RUN python -m pip install --no-cache-dir --progress-bar off "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
# The lockfile records the original PyPI artifact URLs. Exporting its pinned versions and hashes lets
# uv download the identical artifacts through the configured mirror without weakening reproducibility.
RUN uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt \
    && uv venv "${UV_PROJECT_ENVIRONMENT}" \
    && uv pip sync \
        --python "${UV_PROJECT_ENVIRONMENT}/bin/python" \
        --require-hashes \
        /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

COPY app ./app
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-alpine AS runtime

ARG ALPINE_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/parrot/venv/bin:$PATH \
    PYTHONPATH=/app

# Runtime dependencies:
# - bubblewrap isolates executable Skills, scripts, and stdio MCP processes.
# - nodejs/npm run Node Skills and build isolated artifacts.
# - tini forwards signals and reaps child processes for Web and TaskIQ processes.
# - ca-certificates validates TLS connections to explicitly allowed external services.
# Bubblewrap still requires unprivileged user namespaces on the deployment host. Do not weaken the
# container or application sandbox policy to bypass an unavailable sandbox.
RUN set -eu; \
    sed -i \
        -e "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" \
        -e "s|http://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" \
        /etc/apk/repositories \
    && apk add --no-cache bubblewrap ca-certificates nodejs npm tini \
    && command -v bwrap >/dev/null \
    && command -v node >/dev/null \
    && command -v npm >/dev/null \
    && command -v tini >/dev/null \
    && bwrap --version >/dev/null \
    && node --version >/dev/null \
    && npm --version >/dev/null \
    && tini --version >/dev/null \
    && test -r /etc/ssl/certs/ca-certificates.crt \
    && addgroup -S parrot \
    && adduser -S -D -H -h /app -G parrot parrot \
    && mkdir -p /app /etc/parrot \
        /var/lib/parrot/skill-artifacts /var/lib/parrot/skill-builds \
        /var/lib/parrot/skill-packages /var/lib/parrot/skill-sessions \
    && chown -R parrot:parrot /app /var/lib/parrot

WORKDIR /app

ARG PARROT_CONFIG_FILE=config/sit.toml

COPY --from=builder /opt/parrot/venv /opt/parrot/venv
COPY --chown=parrot:parrot alembic ./alembic
COPY --chown=parrot:parrot alembic.ini ./alembic.ini
COPY --chown=parrot:parrot app ./app
COPY ${PARROT_CONFIG_FILE} /etc/parrot/config.toml
RUN chmod 0444 /etc/parrot/config.toml

USER parrot

EXPOSE 8000

ENTRYPOINT ["tini", "--"]
CMD ["parrot", "serve", "--config", "/etc/parrot/config.toml"]
