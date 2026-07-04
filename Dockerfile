FROM python:3.12-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml pyproject.toml
COPY src src
COPY README.md README.md
COPY .env.example .env.example

# Install the package and runtime dependencies. All dependencies ship as
# manylinux wheels (pydantic-core, cryptography, etc.), so no build toolchain
# is required — keeping the image small and the build fast.
RUN pip install --no-cache-dir .

# Run the MCP server. Transport is selected via MCP_TRANSPORT (default stdio);
# the deployment sets MCP_TRANSPORT=http for streamable-HTTP. Auth + stateless
# JSON transport are configured in code (see mcp_instance.py), no monkeypatch.
CMD ["python", "-m", "intervals_mcp_server.server"]
