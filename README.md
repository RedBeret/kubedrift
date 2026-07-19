# kubedrift

> Snapshot your Kubernetes cluster state. Diff two snapshots. Know exactly what changed.

`kubedrift` is a small CLI that captures a point-in-time snapshot of what's running in a cluster — workloads, images, replicas, configmaps, secrets, services, ingresses — and compares any two snapshots to tell you what drifted, categorized as **BREAKING**, **IMAGE**, **ADDITIVE**, or **INFORMATIONAL**.

It's useful anywhere cluster state can change outside your GitOps chain: someone `kubectl edit`s a deployment during an incident, a configmap key quietly disappears, a service selector gets fat-fingered, or you just want to answer "what changed in this namespace since Friday?"

Sister project to [pgdrift](https://github.com/RedBeret/pgdrift), which does the same thing for Postgres schemas.

---

## Quick start

```bash
pipx install git+https://github.com/RedBeret/kubedrift

# Capture current cluster state (all non-system namespaces)
kubedrift snapshot

# Or scope it down
kubedrift snapshot -n prod --context my-cluster --label before-deploy

# Compare two snapshots (exits 1 if anything BREAKING changed)
kubedrift diff snapshots/snapshot_20260718_100000.json snapshots/snapshot_20260718_143000.json

# Watch for drift against a baseline on an interval
kubedrift watch --baseline snapshots/baseline.json -n prod --interval 60

# Pretty-print a snapshot
kubedrift report snapshots/baseline.json

# Full end-to-end demo in a throwaway namespace (kind/minikube/k3s all work)
kubedrift demo
```

The only requirement is a working `kubectl` — kubedrift shells out to it rather than reimplementing auth, so contexts, exec plugins (EKS/GKE/AKS), and whatever else your kubeconfig does all just work.

---

## Diff categories

Every detected change is classified before it's shown:

| Category | Color | Examples |
|---|---|---|
| **BREAKING** | red | Deleted workload/service/configmap/secret, replicas scaled to zero, removed container or env var, removed configmap/secret key, service selector change, removed port or ingress route |
| **IMAGE** | magenta | Any container image change. Separated out because image bumps are the most common intentional change — without their own bucket they'd bury everything else |
| **ADDITIVE** | green | New workload/service/configmap, new env var, new key, scale-up, new port or route |
| **INFORMATIONAL** | yellow | Config/secret value changed behind an unchanged key, resource requests/limits tweaked, service type change, targetPort or ingress backend change |

The judgment is opinionated. If your team disagrees with a classification, open an issue.

`kubedrift diff` exits 1 when anything BREAKING is present (disable with `--no-fail-on-breaking`), so it drops straight into a CI gate:

```yaml
- run: kubedrift snapshot -n prod --label current
- run: kubedrift diff snapshots/baseline.json snapshots/snapshot_*_current.json
```

---

## Snapshot format

Snapshots are plain JSON — human-readable, diff-able with `git diff`, and deterministic (sorted keys, stable formatting), so two snapshots of an unchanged cluster produce identical output.

**Snapshots are safe to commit.** Secret values and inline env values are stored as truncated SHA-256 digests, never plaintext — enough to detect that a value changed, useless for recovering it. Env vars sourced from configmaps/secrets are stored as readable references (`from:secret/db-credentials/password`).

```json
{
  "format_version": 1,
  "captured_at": "2026-07-18T14:30:00+00:00",
  "context": "kind-kubedrift",
  "server_version": "v1.33.1",
  "workloads": {
    "prod/Deployment/parts-api": {
      "replicas": 2,
      "containers": [
        {
          "name": "api",
          "image": "ghcr.io/acme/parts-api:2.4.1",
          "requests": {"cpu": "100m", "memory": "128Mi"},
          "env": [
            {"name": "LOG_LEVEL", "value": "sha256:0d1e2f3a4b5c"},
            {"name": "DB_PASSWORD", "value": "from:secret/db-credentials/password"}
          ]
        }
      ]
    }
  },
  "configmaps": {"prod/app-config": {"keys": {"CACHE_TTL": "sha256:9a8b7c6d5e4f"}}}
}
```

System noise is filtered by default: `kube-system` and friends, `kube-root-ca.crt` configmaps, and service-account token secrets are skipped unless you pass `--include-system`.

---

## Demo

`kubedrift demo` needs any working cluster context and does everything inside a throwaway `kubedrift-demo` namespace: deploys a small stack, snapshots it, then simulates a bad week — an image bump, a scale-to-zero, a deleted deployment, a removed configmap key — and shows you the categorized drift report. Pass `--keep` to poke around afterwards.

With [kind](https://kind.sigs.k8s.io/) that's:

```bash
kind create cluster --name kubedrift
kubedrift demo
kind delete cluster --name kubedrift
```

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Everything downstream of kubectl is pure functions over parsed JSON, so the whole test suite runs without a cluster.

## License

MIT
