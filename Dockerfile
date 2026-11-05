FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV SHELLY_MCP_TRANSPORT=streamable-http
ENV SHELLY_MCP_HOST=0.0.0.0
ENV SHELLY_MCP_PORT=8765

EXPOSE 8765

CMD ["shelly-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"]
