FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    curl \
    git \
    sudo \
    build-essential \
    libffi-dev \
    libssl-dev \
    nodejs \
    npm \
    postgresql-client \
    redis-tools \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code @openai/codex

RUN useradd -m -s /bin/bash dev && \
    echo "dev ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

ENV VIRTUAL_ENV=/home/dev/venv
RUN python -m venv $VIRTUAL_ENV && \
    chown -R dev:dev /home/dev

USER dev

ENV PATH="$VIRTUAL_ENV/bin:/home/dev/.local/bin:$PATH"
ENV NODE_OPTIONS="--dns-result-order=ipv4first"
ENV ANTHROPIC_TIMEOUT=120000

WORKDIR /workspace

# Copy and install dependencies
# Volume mount at runtime will override /workspace, but venv persists at /home/dev/venv
COPY --chown=dev:dev pyproject.toml ./
COPY --chown=dev:dev src/ ./src/
RUN pip install --upgrade pip && \
    pip install -e ".[all]"
RUN mkdir -p /home/dev/.claude /home/dev/.codex

CMD ["bash"]
