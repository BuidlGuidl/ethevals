FROM node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS node
FROM ghcr.io/buidlguidl/ethevals-chain:inputs-d0ef1955a98ec678
USER root
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    apt-get update && apt-get install -y --no-install-recommends libstdc++6 procps && \
    rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json /opt/votes-deps/
RUN cd /opt/votes-deps && npm ci --ignore-scripts && chmod 700 /opt/votes-deps
WORKDIR /workspace
COPY --chown=agent:agent package.json package-lock.json tsconfig.json ./
RUN cp -a /opt/votes-deps/node_modules /workspace/node_modules && \
    chown -R agent:agent /workspace && mkdir /workspace/src && chown agent:agent /workspace/src && \
    ln -s /chain/chain_context.json /workspace/chain_context.json
ENV RPC_URL=http://chain:8545
USER agent
ENTRYPOINT []
CMD ["sleep", "infinity"]
