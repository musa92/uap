# Reference exchange, proxy and a stand-in upstream.
# Stdlib-only Python: the image is the interpreter plus the package.
FROM python:3.12-slim AS base
WORKDIR /app
# Unbuffered, or the startup banner never reaches `docker logs`.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY reference/python/pyproject.toml ./
COPY reference/python/uap ./uap
RUN pip install --no-cache-dir . && rm -rf /root/.cache

FROM base AS exchange
EXPOSE 8787
ENTRYPOINT ["uap", "serve", "--host", "0.0.0.0", "--port", "8787"]

FROM base AS proxy
EXPOSE 8800
ENTRYPOINT ["uap", "proxy", "--host", "0.0.0.0", "--port", "8800"]

# Stands in for vLLM, Ollama or llama.cpp so the demo needs no GPU.
FROM base AS upstream
COPY reference/python/demo/upstream_stub.py ./
EXPOSE 8000
ENTRYPOINT ["python", "upstream_stub.py"]
