FROM python:3.13-slim

WORKDIR /app

COPY app ./app
COPY static ./static
COPY knowledge ./knowledge
COPY run.py ./run.py
COPY README.md ./README.md

ENV AGENT_HOST=0.0.0.0
ENV AGENT_PORT=8765
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434

EXPOSE 8765

CMD ["python3", "run.py"]
