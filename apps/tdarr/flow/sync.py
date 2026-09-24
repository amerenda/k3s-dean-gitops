#!/usr/bin/env python3
"""Push the version-controlled Tdarr flow (flow.json + plugin .js files) into Tdarr.

Tdarr keeps flows in its own DB, so git is the source of truth and this script
applies it. Idempotent: does nothing if the live flow already matches.
Never inserts - if the flow doc is missing it fails loudly (an insert would get
a server-assigned id and the library's flowId would no longer point at it).

Env: TDARR_URL (default in-cluster service), FLOW_ID, FLOW_DIR.
Flag: --dry-run  compare only, never write.
"""
import json
import os
import re
import sys
import time
import urllib.request

URL = os.environ.get("TDARR_URL", "http://tdarr-server.tdarr.svc.cluster.local:8265").rstrip("/")
FLOW_ID = os.environ.get("FLOW_ID", "V0wcPXekg")
FLOW_DIR = os.environ.get("FLOW_DIR", os.path.dirname(os.path.abspath(__file__)))
KEYS = ("name", "description", "tags", "flowPlugins", "flowEdges")
DRY = "--dry-run" in sys.argv


def cruddb(data):
    req = urllib.request.Request(
        URL + "/api/v2/cruddb",
        data=json.dumps({"data": data}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip() else None


def build_desired():
    flow = json.load(open(os.path.join(FLOW_DIR, "flow.json")))
    pat = re.compile(r"^@@file:([\w.-]+)@@$")
    for node in flow["flowPlugins"]:
        code = node.get("inputsDB", {}).get("code")
        m = pat.match(code) if isinstance(code, str) else None
        if m:
            node["inputsDB"]["code"] = open(os.path.join(FLOW_DIR, m.group(1))).read()
    return {k: flow[k] for k in KEYS}


def live_subset(doc):
    return {k: doc.get(k) for k in KEYS}


def wait_for_tdarr():
    for i in range(30):
        try:
            return cruddb({"collection": "FlowsJSONDB", "mode": "getById", "docID": FLOW_ID})
        except Exception as e:  # server still starting / mid-rollout
            print(f"waiting for Tdarr ({e})", flush=True)
            time.sleep(10)
    sys.exit("Tdarr never became reachable")


def main():
    desired = build_desired()
    live = wait_for_tdarr()
    if not live:
        sys.exit(f"flow {FLOW_ID} does not exist in Tdarr; refusing to insert (id would change)")
    if live_subset(live) == desired:
        print(f"flow {FLOW_ID} already in sync")
        return
    changed = [k for k in KEYS if live.get(k) != desired[k]]
    print(f"flow {FLOW_ID} differs in: {changed}", flush=True)
    if DRY:
        print("dry run - not writing")
        return
    cruddb({"collection": "FlowsJSONDB", "mode": "update", "docID": FLOW_ID, "obj": desired})
    after = cruddb({"collection": "FlowsJSONDB", "mode": "getById", "docID": FLOW_ID})
    if not after or live_subset(after) != desired:
        sys.exit("read-back after update does not match desired flow")
    print(f"flow {FLOW_ID} updated and verified")


if __name__ == "__main__":
    main()
