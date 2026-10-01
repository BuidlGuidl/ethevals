"""Check RPC classifications against the pinned Foundry source over the network."""
import json
from pathlib import Path
import re
import urllib.request

from ethevals.images import rpc_filter


def test_rpc_methods_match_pinned_anvil():
    images = Path(rpc_filter.__file__).parent
    pin = re.search(r"^FROM ghcr\.io/foundry-rs/foundry:([^@\s]+)@", (images / "Chain.Dockerfile").read_text())
    assert pin is not None, "Chain.Dockerfile must pin a Foundry tag and digest."
    url = f"https://raw.githubusercontent.com/foundry-rs/foundry/{pin[1]}/crates/anvil/core/src/eth/mod.rs"
    with urllib.request.urlopen(url, timeout=30) as response:
        source = response.read().decode()
    enums = dict(re.findall(r"pub enum (EthRequest|EthPubSub) \{(.*?)^\}", source, re.MULTILINE | re.DOTALL))
    assert set(enums) == {"EthRequest", "EthPubSub"}, "Foundry's RPC enum layout changed."
    methods = set()
    for body in enums.values():
        for attribute in re.findall(r"#\[serde\((.*?)\)\]", body, re.DOTALL):
            methods.update(re.findall(r'\b(?:rename|alias)\s*=\s*"([^"\n]+)"', attribute))
    entries = json.loads((images / "rpc_methods.json").read_text(), object_pairs_hook=list)
    classified = dict(entries)
    assert len(entries) == len(classified), "RPC classifications contain duplicate names."
    assert set(classified.values()) <= {"allow", "deny"}, "Each RPC method must be allow or deny."
    assert methods == set(classified), (
        f"Unclassified RPC methods: {sorted(methods - classified.keys())}; "
        f"stale RPC classifications: {sorted(classified.keys() - methods)}"
    )
