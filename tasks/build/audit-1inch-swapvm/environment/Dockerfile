FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node
FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    ln -s ../lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack && \
    corepack enable && \
    apt-get update && apt-get install -y --no-install-recommends \
      bash coreutils curl libstdc++6 procps ripgrep xz-utils && \
    rm -rf /var/lib/apt/lists/*
ARG REPOSITORY=https://github.com/1inch/swap-vm
ARG COMMIT=60172ba83234bacb793c11564fed3a806b6d3388
# Check out the commit with its submodules, drop every git history, and start one fresh commit.
RUN set -eu; \
    git init -q /work/project; \
    cd /work/project; \
    git fetch -q --depth 1 "$REPOSITORY" "$COMMIT"; \
    git checkout -q FETCH_HEAD; \
    test "$(git rev-parse HEAD)" = "$COMMIT"; \
    git -c url."https://github.com/".insteadOf="git@github.com:" \
        -c url."https://github.com/".insteadOf="ssh://git@github.com/" \
        submodule update -q --init --recursive --depth 1; \
    find . -name .git -prune -exec rm -rf {} +; \
    git init -q -b main; \
    git add -A -f; \
    GIT_AUTHOR_DATE=2026-01-01T00:00:00Z GIT_COMMITTER_DATE=2026-01-01T00:00:00Z \
        git -c user.name=Developer -c user.email=developer@example.com commit -q -m "Initial commit"; \
    chown -R agent:agent /work
USER agent
WORKDIR /workspace
ENTRYPOINT []
CMD ["sleep", "infinity"]
