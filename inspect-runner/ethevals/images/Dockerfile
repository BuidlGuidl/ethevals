FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates tar gzip xz-utils curl git procps ripgrep && rm -rf /var/lib/apt/lists/*
# Install Node here because inspect_swe stages it into a root-owned directory.
RUN case "$TARGETARCH" in \
      amd64) arch=x64; checksum=822780369d0ea309e7d218e41debbd1a03f8cdf354ebf8a4420e89f39cc2e612 ;; \
      arm64) arch=arm64; checksum=f6df68c6793244071f69023a9b43a0cf0b13d65cbe86d55925c28e4134d9aafb ;; \
      *) exit 1 ;; esac && \
    curl -fsSL "https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-${arch}.tar.xz" -o /tmp/node.tar.xz && \
    echo "$checksum  /tmp/node.tar.xz" | sha256sum -c - && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 && rm /tmp/node.tar.xz
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
COPY solc.json /tmp/solc.json
RUN node --input-type=module -e 'import fs from "node:fs"; import crypto from "node:crypto"; \
    const {version, sources} = JSON.parse(fs.readFileSync("/tmp/solc.json")); \
    const {url, sha256} = sources[process.env.TARGETARCH]; \
    const response = await fetch(url); if (!response.ok) throw Error(`solc download: ${response.status}`); \
    const data = Buffer.from(await response.arrayBuffer()); \
    if (crypto.createHash("sha256").update(data).digest("hex") !== sha256) throw Error("solc checksum mismatch"); \
    const dir = `${process.env.HOME}/.svm/${version}`; fs.mkdirSync(dir, {recursive: true}); \
    fs.writeFileSync(`${dir}/solc-${version}`, data, {mode: 0o755});'
RUN forge install OpenZeppelin/openzeppelin-contracts@v5.4.0 --no-git
RUN forge install foundry-rs/forge-std@77041d2ce690e692d6e03cc812b57d1ddaa4d505 --no-git
USER root
RUN mkdir -p /opt/ethevals && cp -a /workspace/lib /opt/ethevals/lib && \
    chown -R root:root /opt/ethevals && chmod -R a-w /opt/ethevals
USER agent
CMD ["sleep", "infinity"]
