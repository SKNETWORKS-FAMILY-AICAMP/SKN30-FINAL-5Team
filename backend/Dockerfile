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
# The integrated home bundle's approval registry names its review evidence, and the loader
# refuses to serve reviewed content unless those files are on disk. They sit
# outside the bundle directory, so shipping only the bundle still failed the
# gate with REVIEW_ARTIFACT_MISSING. Copy the named artifacts and nothing more:
# data/reports as a whole is several megabytes of unrelated analysis output.
# backend/tests/unit/test_home_equipment_bundle_validation.py keeps this list
# and the registry in step.
COPY data/reports/home_equipment_substitution_guides_v1_validation.json \
    data/reports/resistance_band_bodyweight_variant_gap_report_v1.json \
    ./data/reports/

# The exercise detail route moved its guide providers from the
# home-equipment-variants-v1-final bundle to this one, so this is the bundle
# GET /exercises/{id} now reads on every request. Leaving it out makes that
# route answer APPROVED_CATALOG_UNAVAILABLE for every exercise -- the same
# failure the v1 bundle already caused once. The request path opens the
# top-level manifest and these two subtrees only; catalog/ and sources/ are
# 3.8MB it never touches. backend/tests/api/test_exercises.py keeps this
# list and the route in step.
COPY data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/bundle_manifest.json \
    ./data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/
COPY data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/gym_equipment \
    ./data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/gym_equipment
COPY data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/home_equipment \
    ./data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/home_equipment

# `backend.app.domain.rules.fitt` opens these two reviewed references while
# building the agent pool on the V3 decision path, not only during a promotion
# command, so leaving them out of the image makes every V3 routine creation
# raise FileNotFoundError. Copy exactly the two files the module opens:
# data/normalized as a whole is several megabytes of pipeline intermediates.
# backend/tests/unit/test_fitt_policy.py keeps this list and the module in step.
COPY data/normalized/catalog_enrichment_v3_fitt.csv \
    data/normalized/fitt_template_v1.csv \
    ./data/normalized/

RUN chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
