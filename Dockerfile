# Use the official Python slim image
FROM python:3.10-slim

# Install uv inside the container for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    GEMINI_API_KEY=""

# Create and set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy packaging metadata files
COPY pyproject.toml uv.lock ./

# Install dependencies globally in the container using uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy the rest of the application files
COPY . .

# Expose Gradio port
EXPOSE 7860

# Run the Gradio app
CMD ["python", "main.py"]
