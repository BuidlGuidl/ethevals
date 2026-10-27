FROM node:22.22.0-bookworm-slim AS node
FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /workspace
COPY --chown=agent:agent foundry.toml package.json package-lock.json /workspace/
COPY --chown=agent:agent src /workspace/src
RUN npm ci --ignore-scripts \
    && mkdir -p /workspace/script /workspace/test \
    && chown -R agent:agent /workspace
RUN mkdir /opt/deposit-verifier \
    && cp package.json package-lock.json /opt/deposit-verifier/ \
    && cd /opt/deposit-verifier && npm ci --ignore-scripts
RUN ln -s /chain/chain_context.json /workspace/chain_context.json
ENTRYPOINT []
CMD ["sleep", "infinity"]
