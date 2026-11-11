"""Send one test condition to the verifier's wallet session."""
import json
from pathlib import Path
import sys
import urllib.request

session = json.loads(Path("/logs/verifier/session.json").read_text())
command = sys.argv[1]
request = urllib.request.Request(session["control"] + "/" + command,
    json.dumps(sys.argv[2:]).encode(), {"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        print(response.read().decode())
except urllib.error.HTTPError as error:
    print(error.read().decode(), file=sys.stderr)
    sys.exit(1)
