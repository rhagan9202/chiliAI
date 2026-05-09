# Story E10-S12: TLS/HTTPS and secrets management

## Story
As a platform operator, I want the API gateway to serve traffic over TLS and all secrets (API keys, DB credentials, JWT signing keys) to be loaded from environment variables or a secrets provider, so that the platform meets baseline security requirements.

## Acceptance Criteria
1. The nginx configuration in `chili_app/nginx.conf` supports TLS termination with configurable cert paths.
2. The Helm chart values support `tls.enabled`, `tls.secretName` for Kubernetes TLS secrets.
3. All backend config fields that reference secrets (LLM API key, DB credentials, Redis password) use `_env_var` pattern — values are read from environment variables, never from config files.
4. A documentation section in `infra/README.md` describes the required secrets and how to provision them.
5. No secrets are committed to the repository or logged.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | M    | E10-S11      |

## Target Files
- `chili_app/nginx.conf` — add TLS server block with configurable cert paths
- `infra/helm/chili/values.yaml` — add TLS and secrets configuration section
- `infra/helm/chili/templates/ingress.yaml` — TLS ingress configuration
- `backend/config/schema.py` — add `SecretField` pattern for env-var-backed secrets
- `backend/config/loader.py` — env var resolution for secret fields
- `infra/README.md` — add secrets management documentation section

## Reference Files to Read First
- `chili_app/nginx.conf` — current nginx configuration
- `infra/helm/chili/values.yaml` — Helm values from E10-S11
- `backend/config/schema.py` — existing config schema
- `backend/config/loader.py` — existing config loading logic

## Architectural Constraints
- TLS termination happens at the nginx/ingress level, not in the Python backend
- Secret fields in config schema must use a `SecretStr` or custom `EnvSecret` type that reads from env vars at load time
- JWKS URIs, LLM API keys, database passwords, Redis passwords are all secret fields
- The Helm chart must support both cert-manager and manual TLS secret provisioning
- nginx TLS config must enforce TLS 1.2+ and strong cipher suites

## What NOT To Do
- Do NOT commit any real certificates, keys, or secrets to the repository
- Do NOT hardcode secret values in config schema defaults
- Do NOT log secret values at any log level — use `SecretStr` or equivalent masking
- Do NOT implement TLS in the Python backend — TLS terminates at nginx/ingress
- Do NOT create self-signed certificates as part of this story — document the process instead
- Do NOT add secret rotation logic — just document the rotation procedure

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] nginx TLS configuration is valid (`nginx -t` parseable)
- [ ] Helm chart TLS values render correct ingress YAML
- [ ] Secret fields in config schema resolve from env vars
- [ ] `infra/README.md` documents all required secrets
- [ ] No secrets committed to the repository
- [ ] No lint errors (`ruff check`) for modified Python files
- [ ] Type-safe (`pyright --strict` compatible) for modified Python files
