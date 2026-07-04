FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install build dependencies and Python build backend
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python build tool
RUN pip install --no-cache-dir hatchling

# Copy project files
COPY pyproject.toml pyproject.toml
COPY src src
COPY README.md README.md
COPY .env.example .env.example

# Install the package and runtime dependencies
RUN pip install --no-cache-dir .

# Run the MCP server. Transport is selected via MCP_TRANSPORT (default stdio);
# the deployment sets MCP_TRANSPORT=http for streamable-HTTP. Auth + stateless
# JSON transport are configured in code (see mcp_instance.py), no monkeypatch.
CMD ["python", "-m", "intervals_mcp_server.server"]
