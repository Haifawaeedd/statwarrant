# statwarrant MCP server for a Hugging Face Docker Space (or any container host).
# Clients connect to https://<your-space>.hf.space/mcp
FROM python:3.12-slim
ARG STATWARRANT_REF=main
RUN pip install --no-cache-dir "statwarrant[mcp] @ git+https://github.com/Haifawaeedd/statwarrant@${STATWARRANT_REF}"
RUN useradd -m app
USER app
EXPOSE 7860
# Hugging Face sets SPACE_HOST to the public host name; it is used for DNS rebinding protection.
CMD ["sh", "-c", "statwarrant-mcp --http --host 0.0.0.0 --port 7860 ${SPACE_HOST:+--allowed-host $SPACE_HOST}"]
