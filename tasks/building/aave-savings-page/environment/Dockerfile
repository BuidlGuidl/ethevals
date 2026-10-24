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
USER agent
COPY --chown=agent:agent starter/package.json starter/pnpm-lock.yaml starter/.npmrc ./
RUN pnpm install --frozen-lockfile && rm -rf /home/agent/.local/share/pnpm/store
COPY --chown=agent:agent starter/ ./
RUN ln -s /chain/chain_context.json /workspace/chain_context.json
ENTRYPOINT []
CMD ["sleep", "infinity"]
