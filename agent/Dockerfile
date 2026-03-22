FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        iproute2 \
        net-tools \
        procps \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/grapheon/agent /var/lib/grapheon-agent

COPY agent/ /opt/grapheon/agent/
COPY deploy/grapheon-agent.env.example /etc/grapheon-agent.env.example

WORKDIR /var/lib/grapheon-agent

ENTRYPOINT ["/usr/bin/env", "python3", "/opt/grapheon/agent/grapheon_agent.py"]
CMD ["--help"]
