FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates tar gzip curl git procps && rm -rf /var/lib/apt/lists/*
RUN case "$TARGETARCH" in \
      amd64) checksum=73640b01bd9ed29fdb4965085099371f8cf0dbbec3e2086cf54564efc4dcfe88 ;; \
      arm64) checksum=cccf28bdf202289e837a9e21ed213b2b80dc1e806e12f1717bc98a44315c331e ;; \
      *) exit 1 ;; esac && \
    curl -fsSL "https://github.com/foundry-rs/foundry/releases/download/v1.5.1/foundry_v1.5.1_linux_${TARGETARCH}.tar.gz" -o /tmp/foundry.tar.gz && \
    echo "$checksum  /tmp/foundry.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/foundry.tar.gz -C /usr/local/bin forge cast && rm /tmp/foundry.tar.gz
RUN useradd --create-home agent && mkdir /workspace && chown agent:agent /workspace
USER agent
WORKDIR /workspace
# Fetch the fixture's compiler at image build time.
RUN mkdir src && printf 'pragma solidity =0.8.30; contract Warmup {}\n' > src/Warmup.sol && \
    forge build --use 0.8.30 && rm -rf src out cache
RUN forge install OpenZeppelin/openzeppelin-contracts@v5.4.0 --no-git
RUN forge install foundry-rs/forge-std@77041d2ce690e692d6e03cc812b57d1ddaa4d505 --no-git
USER root
RUN mkdir -p /opt/ethevals && cp -a /workspace/lib /opt/ethevals/lib && \
    chown -R root:root /opt/ethevals && chmod -R a-w /opt/ethevals
USER agent
CMD ["sleep", "infinity"]
