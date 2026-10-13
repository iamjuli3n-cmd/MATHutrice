# One image per commit, run as-is on every deployed environment. Its settings
# and secrets come from the environment at start, never from the image: no .env
# is copied in (.dockerignore).

# The exact interpreter .python-version pins, so uv uses it instead of
# downloading one.
FROM python:3.14.7-slim

# uv installs what uv.lock pins: the versions a contributor has locally, with
# nothing resolved at build time.
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first, without the project: this layer stays cached until the
# lock changes. --no-dev: tach is a check, not part of the service.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY mathutrice ./mathutrice
RUN uv sync --frozen --no-dev

# The app always runs behind a proxy that terminates TLS (App Service), whose
# address seen from the container is only known at deploy time. Without
# trusting X-Forwarded-Proto from any address, redirects and links built by the
# app would say http:// on an https:// page.
ENV FORWARDED_ALLOW_IPS="*"

# The commit the image is built from (--build-arg REVISION=...). The app sends
# it back in the X-Revision header of every answer, so a deploy can tell which
# image answers, not only that one does. Last, so it does not bust the layers
# above.
ARG REVISION=unknown
ENV REVISION=$REVISION

# The one process the service runs, as the README starts it: uvicorn, with the
# hourly conversation cleanup running inside it (APScheduler, started in the
# app's lifespan).
EXPOSE 8000
CMD ["uvicorn", "mathutrice.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
