# Security policy

## Deployment boundary

This project is designed for a trusted personal machine or private network.
Do not expose it directly to the public Internet.

For remote access, prefer Tailscale/WireGuard or a reverse proxy with HTTPS.
Bind to loopback unless LAN access is required. `--lan` authentication is a
single shared access token, not a multi-user authorization system.

**A loopback peer is not authentication.** Reverse proxies connect from
`127.0.0.1`, so the server cannot treat "peer is loopback" as "this is the
owner". The loopback bypass is granted only when the `Host` header is also a
loopback name and no forwarding headers (`X-Forwarded-For`, `Forwarded`, ...)
are present. For a reverse proxy you MUST:

1. set `LNTRANS_ALLOWED_HOSTS` to the external hostname (this forces the access
   token on, even when the server binds `127.0.0.1`);
2. preserve the original `Host` header (do not rewrite it to `127.0.0.1`);
3. forward the access token, or use `--require-auth` to require a token even
   for local requests.

Never expose an instance whose startup log did not print an access token.

LAN login uses a same-origin form. The URL and proxy access log never contain
the access token. Successful login issues a random, expiring HttpOnly session
cookie; the master token is not stored in the browser. Write requests require a
same-origin `Origin`/`Sec-Fetch-Site` when the browser supplies them. Host,
Referrer-Policy, CSP, frame and MIME-sniffing checks are enabled, and login /
translation-start attempts are rate-limited.

Plain HTTP on a shared Wi-Fi network is not encrypted. Anyone who can observe
the network may read content or session traffic. Use HTTPS through a trusted
reverse proxy or a private VPN such as Tailscale outside a trusted hotspot.
Set `LNTRANS_ALLOWED_HOSTS` only to hostnames you actually use.

## Sensitive runtime data

The following are never part of the source distribution:

- `.env` and credentials;
- API keys;
- `novels/` and translations;
- `data/`, reading progress, favorites and feedback;
- profiles and recommendation history;
- cover/cache directories and logs.

The v5 runtime must keep application code read-only and mount one writable
data home. Do not place API keys in the data home or inside backup archives.
One data home supports one running server. A second server must fail rather
than share the generation; do not operate the same home on a network filesystem
whose advisory locks are unreliable.

Mutating CLI commands take the same lock. Read-only backup verification may run
at any time, but a backup created during active translation is not a
transactional point-in-time snapshot.

## Reporting a vulnerability

Do not open a public issue containing an API key, private translation, reading
state, absolute host paths, or a working exploit against a deployed instance.
Report privately to the repository maintainer through the hosting platform's
private security advisory feature.

Include:

- affected version and schema version;
- platform and deployment mode;
- minimal reproduction without real user data;
- expected and actual behavior;
- whether the issue can write, delete, expose, or cross-contaminate data.

## Recovery and key compromise

If a key is exposed, revoke it at the provider first. Removing it from logs or
Git history does not make the old key safe. If the data root is suspected to be
corrupted, stop all instances and use a verified backup instead of deleting the
active generation.

If a LAN access token is exposed, stop the server and restart it with a new
`LNTRANS_TOKEN` or `LNTRANS_TOKEN_FILE`. Existing in-memory sessions disappear
on restart. `LNTRANS_TOKEN_FILE` should be outside the data root so backups do
not copy the access secret.

