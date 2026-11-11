FROM python:3.13.7-slim-bookworm@sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d
RUN pip install --no-cache-dir harbor-rewardkit==0.2.4
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/* && curl -fsSL https://claude.ai/install.sh | bash -s -- 2.1.321
COPY judge-settings.json agent_judge.py /opt/
COPY target_checks.py /opt/target_checks.py
COPY check_records.py /opt/check_records.py
WORKDIR /app
