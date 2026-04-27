FROM qdrant/qdrant:latest
# Render injects $PORT (usually 10000). Forward it to Qdrant's HTTP port config.
# The internal QDRANT_URL in the backend still uses 6333, but Render's public
# health check uses whatever port it assigns.
ENTRYPOINT []
CMD ["sh", "-c", "QDRANT__SERVICE__HTTP_PORT=${PORT:-6333} /qdrant/qdrant"]
