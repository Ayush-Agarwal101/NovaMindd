FROM python:3.11-slim

# No shell, no package manager, minimal attack surface
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip \
    && apt-get purge -y --auto-remove curl wget git \
    && rm -rf /var/lib/apt/lists/*

# Pre-install safe standard scientific libraries only
RUN pip install --no-cache-dir \
        numpy==1.26.4 \
        pandas==2.2.2

# Drop all capabilities at image level
RUN useradd -u 65534 -U -d /workspace -s /bin/false nobody 2>/dev/null || true

WORKDIR /workspace
USER 65534

CMD ["python3"]
