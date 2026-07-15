# IdP configuration templates (Keycloak, Okta)

> **Verification status: desk-checked, not live-verified.** These templates were
> produced by reading each IdP's own documentation and chiliAI's `AuthConfig`
> schema side by side, then cross-checking every field and endpoint shape
> against that documentation. **No live Keycloak or Okta tenant was stood up
> against this code** (product-owner ruling, 2026-07-15 — BL-022 stretch is
> test-double-verified only; see `docs/superpowers/specs/2026-07-15-bl022-oidc-hardening-design.md`).
> Standing up a real IdP and running the BFF flow end-to-end against it is the
> recorded residual follow-up — see `docs/backlog/_security.md` story
> `_security.01`.

Every field below is a real `AuthConfig` field (`backend/config/schema.py`).
Read that model before changing this doc — do not invent field names.

```python
class AuthConfig(BaseModel):
    enabled: bool = False
    issuer_url: str | None = None
    audience: str | None = None
    jwks_uri: str | None = None
    roles_claim: str = "roles"
    jwks_cache_seconds: int = Field(default=3600, gt=0)

    # OIDC client (used by the BFF auth router)
    client_id: str | None = None
    client_secret_env_var: str | None = None
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    end_session_endpoint: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    redirect_uri: str | None = None

    # Cookie / session
    cookie_secure: bool = True
    cookie_domain: str | None = None
    session_ttl_seconds: int = Field(default=3600, gt=0)
```

`auth` is a top-level section of the domain `DomainConfig` YAML (sibling of
`graph:`, `vectorstore:`, etc. — see `backend/config/defaults/*.yaml`).

---

## Keycloak

### `auth:` YAML

```yaml
auth:
  enabled: true
  issuer_url: "https://<host>/realms/<realm>"
  audience: "chili-app"   # must equal client_id — see the aud note below
  jwks_uri: "https://<host>/realms/<realm>/protocol/openid-connect/certs"
  roles_claim: "roles"   # a flattened top-level claim — see the mapping note below
  jwks_cache_seconds: 3600

  client_id: "chili-app"
  client_secret_env_var: "OIDC_CLIENT_SECRET"
  authorize_endpoint: "https://<host>/realms/<realm>/protocol/openid-connect/auth"
  token_endpoint: "https://<host>/realms/<realm>/protocol/openid-connect/token"
  end_session_endpoint: "https://<host>/realms/<realm>/protocol/openid-connect/logout"
  scopes: ["openid", "email", "profile"]
  redirect_uri: "https://<api-base>/auth/callback"

  cookie_secure: true
  cookie_domain: "<app-host>"
  session_ttl_seconds: 3600
```

Substitute `<host>`, `<realm>`, `<api-base>`, and `<app-host>` for your
deployment. `<api-base>` is the origin chiliAI's API is reachable at (the BFF
callback lives there, not on the SPA origin).

### IdP-side setup steps

1. **Create a public client** (Keycloak client "Client authentication" =
   **off**, i.e. a public client) — the BFF uses PKCE, not a confidential
   client secret, for the browser-facing authorization-code exchange. If your
   realm requires a confidential client instead, set
   `client_secret_env_var` to an env var name and provision that secret;
   chiliAI's `/auth/callback` sends `client_secret` on the token-exchange
   request either way (`api/routers/_oidc_client.py::OidcClient.exchange_code`).
   **Note:** `client_secret_env_var` must name an environment variable that
   exists at runtime even for public clients (an empty value is acceptable);
   the callback will error if the variable is absent.
2. **Require PKCE with S256.** In the client's Advanced settings, set "Proof
   Key for Code Exchange Code Challenge Method" to `S256`. chiliAI always
   generates an S256 challenge (`generate_pkce_pair` in
   `api/routers/_oidc_client.py`) and never falls back to `plain`.
3. **Register the redirect URI** exactly as `<api-base>/auth/callback` (not
   the SPA origin — the callback is handled by the API, which mints the
   session cookie and redirects the browser to `/`).
4. **Map realm roles onto a flat top-level claim matching `roles_claim`.**
   Keycloak's native realm-role claim is nested (`realm_access.roles`), but
   chiliAI resolves `roles_claim` via a flat, single-level `claims.get(...)`
   lookup (`api/middleware/auth.py::_extract_user`, `api/routers/auth.py`'s
   callback) — it does **not** walk dotted paths into nested claim objects.
   Add a custom Keycloak protocol mapper (client scope → Mappers → create a
   "User Realm Role" mapper, or a script/hardcoded-claim mapper) that emits
   the roles as a **top-level** claim named exactly what `roles_claim`
   configures (`"roles"` above). `coerce_roles()` (`api/middleware/auth.py`)
   accepts either a list of strings or a single string claim value once it
   is a top-level key.
5. **Key rotation posture.** When Keycloak rotates its realm signing keys
   (scheduled rotation or an admin-triggered "Rotate keys" action), tokens
   signed by the new key carry a `kid` chiliAI's cached JWKS document does not
   yet have. `decode_token` (`api/middleware/auth.py`) reads the token's `kid`
   from its unverified header, and if that `kid` is absent from the cached
   JWKS, calls `JwksCache.force_refresh` — a forced refetch of `jwks_uri`,
   throttled to at most once per URI per 30 seconds regardless of how many
   unknown-`kid` tokens arrive in that window. In practice: the **first**
   post-rotation login triggers one extra JWKS fetch and succeeds; nothing
   needs restarting, and the realm's old key can be removed once you're
   confident no still-valid token was signed with it. **Bounded worst case:**
   If the 30-second forced-refresh window was consumed just before a rotation
   (by unknown-`kid` noise or a transient JWKS fetch failure), tokens signed
   by the new key receive 401s for at most 30 seconds, then recover
   automatically on the next unknown-`kid` token — no restart needed.
6. **`aud` must equal `client_id`.** Per OIDC Core, an ID token's `aud` claim
   is the client_id of the client the token was issued to — Keycloak sets
   this automatically. `decode_token` (`api/middleware/auth.py`) checks
   `aud == AuthConfig.audience` exactly, so `audience` in the YAML above must
   match `client_id` unless you've added a Keycloak "Audience" protocol
   mapper that appends an additional value to `aud` (in which case
   `audience` may be that additional value instead, since `jose`'s audience
   check accepts a list-valued `aud` containing the configured audience).

---

## Okta

### `auth:` YAML

```yaml
auth:
  enabled: true
  issuer_url: "https://<org>.okta.com/oauth2/default"
  audience: "<okta-client-id>"   # must equal client_id — see the aud note below
  jwks_uri: "https://<org>.okta.com/oauth2/default/v1/keys"
  roles_claim: "groups"
  jwks_cache_seconds: 3600

  client_id: "<okta-client-id>"
  client_secret_env_var: "OIDC_CLIENT_SECRET"
  authorize_endpoint: "https://<org>.okta.com/oauth2/default/v1/authorize"
  token_endpoint: "https://<org>.okta.com/oauth2/default/v1/token"
  end_session_endpoint: "https://<org>.okta.com/oauth2/default/v1/logout"
  scopes: ["openid", "email", "profile", "groups"]
  redirect_uri: "https://<api-base>/auth/callback"

  cookie_secure: true
  cookie_domain: "<app-host>"
  session_ttl_seconds: 3600
```

`https://<org>.okta.com/oauth2/default` is Okta's **org authorization
server** (the one every Okta org gets by default); if you've provisioned a
**custom** authorization server instead, `issuer_url`/`jwks_uri`/the three
endpoint URLs all change to
`https://<org>.okta.com/oauth2/<custom-auth-server-id>/...` — keep them
consistent (mixing a custom-server issuer with the default server's JWKS URI,
or vice versa, will decode-fail on `iss` mismatch).

### IdP-side setup steps

1. **Create an "OIDC – Web Application" app integration** in Okta, grant type
   **Authorization Code**, and require **PKCE** (Okta calls this "Require PKCE
   as additional verification" — enable it; the BFF always sends a PKCE
   challenge and never falls back to a plain confidential-client exchange).
2. **Register the redirect URI** as `<api-base>/auth/callback` under "Sign-in
   redirect URIs", and, if you use `/auth/logout`'s IdP round-trip, the
   post-logout redirect target under "Sign-out redirect URIs".
3. **Add the `groups` scope and claim.** Okta's default authorization server
   does not include a `groups` claim on the ID token unless a claim is
   defined for it (Security → API → Authorization Servers → your server →
   Claims → Add Claim, value type "Groups", token type "ID Token", filter to
   the groups you want exposed). Point `AuthConfig.roles_claim` at whatever
   claim name you configure (`"groups"` above is the conventional choice).
4. **Key rotation posture** is identical to Keycloak's: Okta rotates its JWKS
   signing key on its own schedule (typically every ~2 years by default, or
   on-demand via Admin → Security → API), and chiliAI's kid-triggered forced
   refetch (throttled to once per URI per 30 seconds) picks up the new key on
   the first token that carries it — no restart, no manual cache bust.
5. **`aud` must equal `client_id`.** Per OIDC Core, an ID token's `aud` claim
   is the client_id of the app it was issued to — Okta sets this
   automatically for both the org authorization server and a custom
   authorization server's ID tokens. `decode_token` checks `aud ==
   AuthConfig.audience` exactly, so `audience` above must match `client_id`.
   (A **custom** authorization server's *access* tokens carry a separate
   resource-server audience — e.g. `api://chili` — configured on the
   authorization server itself; that value is irrelevant here unless a
   deployment configures chiliAI to validate access tokens instead of ID
   tokens, which the BFF flow above does not do by default.)

---

## What chiliAI validates

| Check | How | Where |
|---|---|---|
| RS256 signature | `jwt.decode(..., algorithms=["RS256"])` against the cached/refetched JWKS | `api/middleware/auth.py::decode_token` |
| `iss` | Must equal `AuthConfig.issuer_url` | `decode_token` |
| `aud` | Must equal `AuthConfig.audience` | `decode_token` |
| `exp` | Standard JWT expiry check (via `jose`) | `decode_token` |
| id_token `nonce` | **id_token flows only** (truthy `id_token` present) — compared against the nonce stored alongside the PKCE verifier at `/auth/login` time | `api/routers/auth.py::callback` |
| kid-triggered JWKS refetch | Unknown `kid` in the token header forces one refetch per JWKS URI, throttled to once per 30 seconds | `api/middleware/auth.py::JwksCache.force_refresh` |

**Not yet:**

- **Refresh-token rotation** — refresh tokens are stored and reused as-is;
  rotation-on-use and reuse detection are not implemented. Tracked as
  `_security.08` in `docs/backlog/_security.md`.
- **Back-channel logout** — `/auth/logout` only clears chiliAI's own session
  and (optionally) redirects to the IdP's end-session endpoint; there is no
  listener for an IdP-initiated back-channel logout push. Out of scope for
  this story; not currently tracked as a separate backlog item.

## Why only Keycloak and Okta

This story's design note (`docs/superpowers/specs/2026-07-15-bl022-oidc-hardening-design.md`
§5) scopes multi-IdP support out explicitly. Auth0, Cognito, and Google
Workspace templates are not covered here; add them as a follow-up story if a
deployment needs one, following the same schema-fields-first approach as
this doc.
