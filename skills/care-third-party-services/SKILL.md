---
name: care-third-party-services
description: How a CARE plugin integrates a third-party service (LiveKit, an LLM provider, an SMS gateway, a payment processor) through the backend — the credential-broker pattern, minting short-lived scoped client tokens, verifying signed inbound webhooks, client-facing vs server-facing URLs, secret storage, and outbound-call resilience. Use whenever the plugin talks to any external service or the browser must connect directly to one.
---

# Third-Party Services

Most non-trivial plugins broker an external service. The security model is the whole game:

> **The browser must never hold the third-party credential.**
> The plugin backend holds the API key/secret, authorises the CARE user, and mints a
> **short-lived, narrowly-scoped** token for that one user and that one resource.

## The four-legged auth chain

```
   ┌──────────┐  1. CARE JWT / OTP token        ┌────────────────┐
   │ Browser  │ ──────────────────────────────► │ Plugin backend │
   │          │ ◄────────────────────────────── │  (holds secret)│
   └────┬─────┘  2. ephemeral scoped 3P token   └───────┬────────┘
        │                                               │
        │ 3. connect directly, using that token         │ 4. management API
        ▼                                               ▼  (api key + secret)
   ┌─────────────────────────────────────────────────────────────┐
   │                    Third-party service                       │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ 5. signed webhook
                                 ▼
                        Plugin backend (verifies signature)
```

| Leg | Auth mechanism |
| --- | --- |
| 1. Browser → CARE | `care_access_token` or `care_patient_token` (see `care-auth-contexts`) |
| 2. CARE → Browser | A minted third-party token, TTL-bounded, scoped to one resource |
| 3. Browser → 3P | The minted token. The browser never sees the API secret. |
| 4. CARE → 3P | API key + secret, server-side only |
| 5. 3P → CARE | Signature verification on the raw request body. **Not** the CARE JWT. |

## Leg 2 — minting client tokens

Two rules, both load-bearing:

**Authorise first.** Check that this CARE user is entitled to this resource, right now, before
minting anything.

**Never take identity or grants from the client.** Derive them server-side from `request.user`
and the database. A client-supplied identity is an impersonation vulnerability; client-supplied
grants are a privilege escalation.

```python
@action(detail=True, methods=["POST"])
def join(self, request, *args, **kwargs):
    session = self.get_object()

    # 1. Authorise against our own data model.
    participant = resolve_participant(session, request.user)
    if not participant:
        raise PermissionDenied("You are not a participant of this session")

    # 2. Authorise against time/state windows.
    ensure_joinable(session)

    # 3. Mint. Identity and grants come from the DB, never the request body.
    display_name = request.user.get_full_name() or request.user.username
    return Response(build_join_payload(session, participant, display_name))
```

```python
def mint_access_token(room_name, identity, name, can_publish, metadata=None) -> str:
    """Mint an access token. Identity and grants are never taken from the client."""
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,          # scoped to ONE room
        can_publish=can_publish, # capability derived from the participant's role
        can_publish_data=can_publish,
        can_subscribe=True,
    )
    return (
        api.AccessToken(plugin_settings.X_API_KEY, plugin_settings.X_API_SECRET)
        .with_identity(identity)
        .with_name(name)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=plugin_settings.X_TOKEN_TTL_MINUTES))  # short
        .to_jwt()
    )
```

Checklist for any minted token:

- [ ] Scoped to a single resource (room/document/bucket path), not a wildcard.
- [ ] Capabilities derived from the caller's role (a patient may not be able to publish, moderate,
      or record).
- [ ] Short TTL (minutes, not days). It is re-mintable on demand — there is no reason to issue
      a long-lived one.
- [ ] Identity is a namespaced, non-guessable server-side value (`user:{external_id}`,
      `patient:{external_id}`), never a raw phone number, email, or database PK.
- [ ] Minted **per join**, never cached in your DB or returned by a list endpoint.

## ⚠️ Client-facing vs server-facing URLs

The URL the **browser** uses and the URL the **backend container** uses are usually different,
especially in Docker. Keep them as two settings.

```python
DEFAULTS = {
    # Client facing — resolved by the browser. ws://localhost:7880, wss://livekit.example.com
    "CONNECT_LIVEKIT_URL": "",
    # Server side — resolved from inside the backend container. http://host.docker.internal:7880
    "CONNECT_LIVEKIT_HOST": "",
}
```

```python
def livekit_host() -> str:
    """The http(s) url used for the management API."""
    host = plugin_settings.CONNECT_LIVEKIT_HOST
    if host:
        return host
    # Fall back to deriving it from the client URL.
    url = plugin_settings.CONNECT_LIVEKIT_URL
    if url.startswith("wss://"):
        return "https://" + url[len("wss://"):]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://"):]
    return url
```

Symptom of conflating them: works in production, connection-refused in local Docker (or vice
versa). `localhost` inside a container is the container, not your machine.

## The `config/` endpoint

Publish only the client-safe subset. This is what stops the frontend hardcoding a URL and what
keeps the secret server-side.

```python
class ConfigView(APIView):
    """Public client config. The API secret never leaves the backend."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response({
            "enabled": bool(plugin_settings.CONNECT_LIVEKIT_URL),
            "livekit_url": plugin_settings.CONNECT_LIVEKIT_URL,   # client-facing URL only
            "join_buffer_minutes": plugin_settings.CONNECT_JOIN_BUFFER_MINUTES,
            "recording_enabled": plugin_settings.CONNECT_RECORDING_ENABLED,
        })
```

Never return `*_API_SECRET`, `*_API_KEY`, or a server-side host from here. Mirror it at
`otp/config/` for the patient portal, with the same or a narrower payload.

## Leg 5 — inbound webhooks

A webhook is **not** authenticated by the CARE JWT — the third party has no CARE session. It is
authenticated by a signature over the request body.

```python
class LiveKitWebhookView(APIView):
    """
    Receives room events.

    Not protected by the CARE JWT; the Authorization header carries a signed JWT
    verified with the shared API key/secret.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise AuthenticationFailed("Missing webhook signature")
        try:
            # Verify against the RAW body — not request.data.
            event = verify_webhook(request.body, auth_header)
        except Exception as exc:
            raise AuthenticationFailed("Invalid webhook signature") from exc

        session = TeleSession.objects.filter(room_name=event.room.name).first()
        if not session:
            logger.warning("Webhook for unknown room %s", event.room.name)
            return Response({"detail": "ignored"})     # 200, not 404

        handler = {
            "participant_joined": self.handle_participant_joined,
            "room_finished": self.handle_room_finished,
        }.get(event.event)
        if handler:
            handler(session, event, at)
        return Response({"detail": "ok"})
```

Non-obvious requirements:

- **Verify against `request.body`**, the raw bytes. `request.data` has been parsed and
  re-serialising it will not reproduce the signed payload.
- **`authentication_classes = []`** — leaving the default on makes DRF reject the request before
  your signature check runs.
- **Return 200 for unknown/irrelevant events.** A 404 or 500 makes the provider retry, and most
  back off exponentially into a retry storm. "Ignored" is a success.
- **Be idempotent.** Webhooks are delivered at-least-once and out of order. Guard state
  transitions (`if session.status == SCHEDULED:`), don't blindly increment.
- **Trust the event, not the clock.** Use the provider's `created_at` for timestamps, since
  delivery may be delayed.
- The route lives in your plugin's `urls.py`, so its public URL is
  `/api/care_<name>/<provider>/webhook/`. Give the provider that exact path.

### Reaching localhost in development

The provider must reach your backend. Options: run the service in the same Docker network
(`http://host.docker.internal:9000`), or tunnel with `cloudflared` / `ngrok` and point the
provider's webhook config at the tunnel URL. Note that a tunnel URL changes on restart.

## Leg 4 — outbound calls

- **Always set a timeout.** An external service hanging must not hang a CARE request thread.
- **Do slow or non-critical work in celery**, not in the request cycle.
- **Fail soft for cleanup operations.** Log, don't raise:

```python
def close_room(room_name: str) -> None:
    """Disconnect everyone and delete the room. Failures are logged, not raised."""
    try:
        asyncio.run(_close_room(room_name))
    except Exception:
        logger.exception("Failed to close room %s", room_name)
```

- **Import the SDK inside the function**, not at module top level, so an optional dependency or a
  slow import never blocks Django startup.
- **Never let a client supply the destination URL.** Building a request to a client-provided host
  is SSRF. Hosts come from settings only.
- Remember the celery container needs its own editable install of the plugin
  (see `care-backend-plugin`) or your async integration silently runs stale code.

## Secrets

- Declare credentials in `REQUIRED_SETTINGS` so a misconfigured deploy fails loudly at boot
  rather than at the first user's click.
- Supply them via `Plug(configs={...})` or environment variables — production should prefer env
  / `ADDITIONAL_PLUGS`.
- **Never commit a real key.** `plug_config.py` lives in the core repo; a key committed there is
  a key leaked to everyone with repo access. Commit placeholders only.
- Never log a secret, and never echo one back through `config/`.

## Frontend side

```ts
// 1. Read client config (never contains secrets)
const config = await API.config();

// 2. Ask CARE to authorise + mint, at the moment of use
const { token, url } = await API.sessions.join(sessionId);

// 3. Connect directly to the third party
await room.connect(url ?? config.livekit_url, token);
```

- Fetch the token **on the action**, not on page load — TTLs are short.
- Never persist it to `localStorage`.
- Handle expiry by re-calling the mint endpoint, not by extending the TTL.
- Lazy-load the SDK; it is usually large (LiveKit ≈ 600 kB) and must stay out of the manifest
  chunk (see `care-frontend-plugin`).

## Checklist

- [ ] API secret exists only in backend settings; never in `config/`, logs, or the bundle.
- [ ] Authorisation happens before minting, against your own models and time windows.
- [ ] Identity and grants derived server-side; nothing security-relevant read from the request body.
- [ ] Token scoped to one resource with a short TTL, minted per action.
- [ ] Separate client-facing and server-facing URL settings.
- [ ] Webhook verifies a signature over the raw body, with `authentication_classes = []`.
- [ ] Webhook is idempotent and returns 200 for unknown events.
- [ ] Outbound calls have timeouts; cleanup failures are logged, not raised.
- [ ] Destination hosts come from settings, never from the client.
- [ ] Credentials in `REQUIRED_SETTINGS`; no real keys committed.
