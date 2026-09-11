# kubernetes-mcp

Read-only Kubernetes MCP server (`flux159/mcp-server-kubernetes`), exposing
`kubectl_get`/`kubectl_describe`/`kubectl_logs`/etc. as MCP tools against
this cluster's in-cluster ServiceAccount (`kubernetes-mcp-sa`).

## RBAC

RBAC is split across two ClusterRoles bound to `kubernetes-mcp-sa`:

- `view` (built-in) — namespaced core/apps resources, plus any CRD whose
  controller opted into `aggregate-to-view: "true"` (most don't).
- `kubernetes-mcp-extra-view` (`clusterrole-extra-view.yaml`) — explicit
  grant for cluster-scoped resources (`nodes`, `persistentvolumes`) and the
  CRD groups this cluster actually uses that `view` doesn't cover
  (ArgoCD, Traefik, prometheus-operator, Longhorn, MetalLB, cert-manager,
  external-secrets, KEDA, GitHub ARC). See
  `Areas/Infrastructure/notes/kubernetes-mcp-rbac-gap-2026-09-11.md` in the
  Obsidian vault for the full audit of what's covered vs. deliberately
  excluded (`secrets`, RBAC objects, CRDs themselves).

Adding a CRD to an already-granted group needs no changes (wildcarded
`resources: ["*"]` per apiGroup). A brand-new apiGroup needs one more block
in `clusterrole-extra-view.yaml`.

## Known wrapper limitation — do not call `kubectl_reconnect` reflexively

`kubectl_reconnect` discards the wrapper's cached discovery client and
forces a full API-discovery rebuild against every resource type in the
cluster (~180+ here), under client-side rate limiting. The wrapper's
subprocess model is synchronous and blocks its single Node.js event loop
during this rebuild, so **every** tool call — including a trivial `ping` —
can hang for several minutes while it runs, indistinguishable from the
server being dead.

If a call hangs or times out: check the pod's own logs first
(`kubectl -n mcp-kubernetes-mcp logs -l app=kubernetes-mcp-server -c server`)
before reaching for `kubectl_reconnect` — a fast `Forbidden`/`NotFound` in
the logs means it's an RBAC gap (fix the ClusterRole), not a connection
problem `kubectl_reconnect` would fix. Readiness/liveness exec probes
(see `deployment.yaml`) detect this wedge and self-heal it (readiness
pulls the pod out of rotation in ~30s, liveness restarts it after ~2min)
without needing a manual restart.

Full incident history: `Incidents/2026-09-11-kubernetes-mcp-rbac-gap.md`
and `Areas/Infrastructure/Plans/kubernetes-mcp-rbac-fix.md` in the
Obsidian vault.
