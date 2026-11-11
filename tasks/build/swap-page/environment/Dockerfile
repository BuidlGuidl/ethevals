FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node
FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    apt-get update && apt-get install -y --no-install-recommends \
      bash coreutils curl libstdc++6 procps ripgrep xz-utils && \
    rm -rf /var/lib/apt/lists/* && \
    npm install --global pnpm@9.14.2 && npm cache clean --force
WORKDIR /workspace
COPY verifier/package.json verifier/package-lock.json /root/savings-verifier/
RUN cd /root/savings-verifier && npm ci --ignore-scripts && \
    apt-get update && \
    (npx playwright install-deps --dry-run chromium || test "$?" = 1) > /tmp/browser-deps && \
    sed -n 's/^  \([a-z0-9][a-z0-9.+:-]*\)$/\1/p' /tmp/browser-deps > /tmp/browser-packages && \
    test -s /tmp/browser-packages && \
    xargs apt-get install -y --download-only --no-install-recommends < /tmp/browser-packages && \
    mkdir -p /root/savings-libs && \
    for package in /var/cache/apt/archives/*.deb; do dpkg-deb -x "$package" /root/savings-libs; done && \
    PLAYWRIGHT_BROWSERS_PATH=/root/savings-browsers npx playwright install chromium && \
    chmod 700 /root/savings-verifier /root/savings-browsers /root/savings-libs && \
    rm -f /var/cache/apt/archives/*.deb && \
    npm cache clean --force && rm -rf /var/lib/apt/lists/*
COPY verifier/fonts.conf /root/savings-fonts.conf
USER agent
COPY --chown=agent:agent starter/package.json starter/pnpm-lock.yaml starter/.npmrc ./
RUN pnpm install --frozen-lockfile && rm -rf /home/agent/.local/share/pnpm/store
COPY --chown=agent:agent starter/ ./
RUN ln -s /chain/chain_context.json /workspace/chain_context.json
ENTRYPOINT []
CMD ["sleep", "infinity"]
