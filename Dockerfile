# Multi-stage Dockerfile for VaporRAM
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    make \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Build C SIMD engine
RUN make -C c

FROM ubuntu:24.04 AS runner
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app

EXPOSE 8000
CMD ["python3", "openai_server.py"]
