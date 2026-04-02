# Stage 1: Build stage
FROM python:3.9-slim AS build

WORKDIR /app

# Install requirements before code so that the Docker layer can be cached if requirements don't change
# Install it into a venv so it can be copied to the runtime stage without copying all the build dependencies
RUN python -m venv venv

COPY ./databoard_core/requirements.txt /tmp/requirements.txt
RUN ./venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY ./databoard_server/container/celery/requirements.txt /tmp/requirements.txt
RUN ./venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt

# Install databoard core libraries
COPY ./databoard_core /app/databoard_core/
RUN ./venv/bin/python -m pip install -e ./databoard_core

# Install databoard server component
COPY ./databoard_server/src /app/src/
#COPY ./data /app/data/

# Stage 2: Runtime stage
FROM python:3.9-slim
WORKDIR /app

COPY --from=build /app /app

# Set the PATH to use the virtual environment
ENV PATH="/app/venv/bin:$PATH"

# Run the Celery worker
CMD ["celery", "-A", "src.jobs.worker.celery", "worker", "-l", "info"]