FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
ARG REPOSITORY=https://github.com/automata-network/automata-dcap-attestation
ARG COMMIT=2d8b6b3dd35643081fa7fd98bbb1323a0601b2bb
USER root
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
