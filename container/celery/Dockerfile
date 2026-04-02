# Stage 1: Build stage
FROM python:3.9-slim AS build

WORKDIR /app

# Install databoard server component
COPY ./databoard_server/container/celery/requirements.txt .
RUN python -m venv venv && \
    ./venv/bin/python -m pip install --no-cache-dir -r requirements.txt
COPY ./databoard_server/src /app/src/
#COPY ./data /app/data/

# Install databoard core libraries
COPY ./databoard_core /app/databoard_core/
RUN pip install --no-cache-dir -r /app/databoard_core/requirements.txt
RUN pip install -e ./databoard_core

# Stage 2: Runtime stage
FROM python:3.9-slim
WORKDIR /app

COPY --from=build /app /app

# Set the PATH to use the virtual environment
ENV PATH="/app/venv/bin:$PATH"

# Run the Celery worker
CMD ["celery", "-A", "src.jobs.worker.celery", "worker", "-l", "info"]