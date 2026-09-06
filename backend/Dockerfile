# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.11.2 AS uv

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
# A promotion command can only import a bundle that is inside the image.
# Leaving the current release out turns the import into a hand-mounted step
# that no build reproduces. v2.0.1 stays because the deployment README still
# documents its promotion path.
COPY data/generated/exercise-catalog-v2.0.1-final/backend_bundle \
    ./data/generated/exercise-catalog-v2.0.1-final/backend_bundle
COPY data/generated/exercise-catalog-v2.0.4-final/backend_bundle \
    ./data/generated/exercise-catalog-v2.0.4-final/backend_bundle
COPY data/generated/exercise-catalog-v2.0.6-final/backend_bundle \
    ./data/generated/exercise-catalog-v2.0.6-final/backend_bundle
# The exercise detail route reads this bundle on every request, not just during
# a promotion command, so leaving it out of the image made GET /exercises/{id}
# answer APPROVED_CATALOG_UNAVAILABLE for every exercise in the catalog.
COPY data/generated/home-equipment-variants-v1-final/backend_bundle \
    ./data/generated/home-equipment-variants-v1-final/backend_bundle
# That bundle's approval registry names its review evidence, and the loader
# refuses to serve reviewed content unless those files are on disk. They sit
# outside the bundle directory, so shipping only the bundle still failed the
# gate with REVIEW_ARTIFACT_MISSING. Copy the named artifacts and nothing more:
# data/reports as a whole is several megabytes of unrelated analysis output.
# backend/tests/unit/test_home_equipment_bundle_validation.py keeps this list
# and the registry in step.
COPY data/reports/home_equipment_substitution_guides_v1_validation.json \
    data/reports/resistance_band_bodyweight_variant_gap_report_v1.json \
    ./data/reports/

RUN chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
