# Use official Python image
FROM python:3.11

# Set the working directory
WORKDIR /

# Install system dependencies and Poetry
RUN apt-get update && apt-get install -y curl && \
    curl -sSL https://install.python-poetry.org | python3 - && \
    export PATH="$HOME/.local/bin:$PATH"

# Copy the project files
COPY pyproject.toml poetry.lock ./

# Install dependencies with extras
RUN $HOME/.local/bin/poetry install --extras server --no-dev --no-interaction --no-ansi

# Copy the rest of the application
COPY . .

# Expose the application port
EXPOSE 5002

# Run the FastAPI application with required flags
CMD ["bash", "-c", "export PATH=\"$HOME/.local/bin:$PATH\" && poetry run python main.py --server --host 0.0.0.0 --port 5002"]
