# Use an official Python runtime as a base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install server component
COPY ./databoard_server/container/fastapi/requirements.txt .
COPY ./databoard_server/src /app/src/
RUN pip install --no-cache-dir -r requirements.txt
#COPY ./data /app/data/

# Install databoard core libraries
COPY ./databoard_core /app/databoard_core/
RUN pip install --no-cache-dir -r /app/databoard_core/requirements.txt
RUN pip install -e ./databoard_core

# Download models
#RUN python -m spacy download de_core_news_sm
#RUN python /app/src/scripts/install.py

# Expose the port that FastAPI will run on
EXPOSE 8000

# Command to run the FastAPI application using Uvicorn
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
