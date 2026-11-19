"""Third-party tools a brand can connect. `env` is the variable the vs engine reads the key from (as in the plugin's
`vs keys`), so a worker running a brand's job gets exactly that brand's keys and nothing else.

`verify` makes one read-only call with the key and returns (ok, account label, error). It never spends credits.
Keys that go in a query string are never put into error messages or logs."""
from dataclasses import dataclass, field
from typing import Callable

import httpx

TIMEOUT = 10.0


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    category: str                     # voice | avatar | generation | stock | footage | ai
    env: str | None                   # variable the vs engine reads
    used_for: str
    how_to_get: str
    auth: str = "api_key"             # api_key | oauth (sign in on the provider's page; MCP servers)
    paid: bool = False
    verify: Callable[[str], tuple[bool, str, str]] | None = field(default=None, compare=False, repr=False)
    available: bool = True


def _get(url, **kw):
    return httpx.get(url, timeout=TIMEOUT, **kw)


def _fail(r: httpx.Response) -> tuple[bool, str, str]:
    if r.status_code in (401, 403):
        return False, "", "the key was refused (wrong key, revoked, or missing permissions)"
    if r.status_code == 429:
        return False, "", "rate limited while checking: try again in a minute"
    return False, "", f"unexpected answer from the provider (HTTP {r.status_code})"


def _elevenlabs(key):
    r = _get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": key})
    if r.status_code != 200:
        return _fail(r)
    sub = r.json().get("subscription") or {}
    left = (sub.get("character_limit") or 0) - (sub.get("character_count") or 0)
    tier = sub.get("tier") or "account"
    return True, f"{tier.title()} plan · {left:,} characters left" if sub else "ElevenLabs account", ""


def _heygen(key):
    r = _get("https://api.heygen.com/v2/user/remaining_quota", headers={"X-Api-Key": key})
    if r.status_code != 200:
        return _fail(r)
    q = (r.json().get("data") or {}).get("remaining_quota")
    return True, f"{q} credits left" if q is not None else "HeyGen account", ""


def _openai(key):
    r = _get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
    return (True, "OpenAI API key", "") if r.status_code == 200 else _fail(r)


def _gemini(key):
    r = _get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 1})
    return (True, "Google AI Studio key", "") if r.status_code == 200 else _fail(r)


def _pexels(key):
    r = _get("https://api.pexels.com/v1/curated", params={"per_page": 1}, headers={"Authorization": key})
    return (True, "Pexels API key", "") if r.status_code == 200 else _fail(r)


def _pixabay(key):
    r = _get("https://pixabay.com/api/", params={"key": key, "q": "sky", "per_page": 3})
    return (True, "Pixabay API key", "") if r.status_code == 200 else _fail(r)


def _unsplash(key):
    r = _get("https://api.unsplash.com/photos", params={"per_page": 1}, headers={"Authorization": f"Client-ID {key}"})
    return (True, "Unsplash access key", "") if r.status_code == 200 else _fail(r)


def _freesound(key):
    r = _get("https://freesound.org/apiv2/search/text/", params={"query": "door", "page_size": 1, "token": key})
    return (True, "Freesound API key", "") if r.status_code == 200 else _fail(r)


def _jamendo(key):
    r = _get("https://api.jamendo.com/v3.0/tracks/", params={"client_id": key, "limit": 1, "format": "json"})
    ok = r.status_code == 200 and (r.json().get("headers") or {}).get("status") == "success"
    return (True, "Jamendo client ID", "") if ok else (False, "", "the client ID was refused")


def _dropbox(key):
    r = httpx.post("https://api.dropboxapi.com/2/users/get_current_account", timeout=TIMEOUT,
                   headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        return _fail(r)
    d = r.json()
    return True, f"{(d.get('name') or {}).get('display_name', '')} · {d.get('email', '')}".strip(" ·"), ""


PROVIDERS: dict[str, Provider] = {p.id: p for p in [
    Provider("higgsfield", "Higgsfield", "generation", None, "AI video and image generation, ads, avatars",
             "Connected by signing in with the client's Higgsfield account (workspace chosen at sign-in)",
             auth="oauth", paid=True),
    Provider("elevenlabs", "ElevenLabs", "voice", "ELEVENLABS_API_KEY", "Voiceover, voice cloning, dubbing",
             "elevenlabs.io → Profile → API keys", paid=True, verify=_elevenlabs),
    Provider("heygen", "HeyGen", "avatar", "HEYGEN_API_KEY", "Avatars and voiceover with word timestamps",
             "app.heygen.com → Settings → API", paid=True, verify=_heygen),
    Provider("openai", "OpenAI", "ai", "OPENAI_API_KEY", "Voiceover (TTS) and transcription",
             "platform.openai.com → API keys", paid=True, verify=_openai),
    Provider("gemini", "Google Gemini", "ai", "GEMINI_API_KEY", "Music beds (Lyria) and TTS",
             "aistudio.google.com → Get API key", paid=True, verify=_gemini),
    Provider("gdrive", "Google Drive", "footage", "GOOGLE_DRIVE_API_KEY", "Faster, complete listing of Drive folders",
             "console.cloud.google.com → APIs & Services → Credentials → API key (enable the Drive API)"),
    Provider("dropbox", "Dropbox", "footage", "DROPBOX_TOKEN", "List shared folders without downloading the zip",
             "dropbox.com/developers/apps → your app → Generate access token", verify=_dropbox),
    Provider("pexels", "Pexels", "stock", "PEXELS_API_KEY", "Stock video and photos", "pexels.com/api", verify=_pexels),
    Provider("pixabay", "Pixabay", "stock", "PIXABAY_API_KEY", "Stock video, photos and music", "pixabay.com/api/docs",
             verify=_pixabay),
    Provider("unsplash", "Unsplash", "stock", "UNSPLASH_ACCESS_KEY", "Stock photos", "unsplash.com/developers",
             verify=_unsplash),
    Provider("freesound", "Freesound", "stock", "FREESOUND_API_KEY", "Sound effects", "freesound.org/apiv2/apply",
             verify=_freesound),
    Provider("jamendo", "Jamendo", "stock", "JAMENDO_CLIENT_ID", "Music", "devportal.jamendo.com", verify=_jamendo),
]}


def verify(provider: str, key: str) -> tuple[bool | None, str, str]:
    """(True, label, "") verified; (False, "", why) refused; (None, "", "") this provider can't be checked."""
    p = PROVIDERS[provider]
    if not p.verify:
        return None, "", ""
    try:
        return p.verify(key)
    except httpx.HTTPError as e:
        return False, "", f"could not reach {p.name} ({e.__class__.__name__}): try again"
    except ValueError:
        return False, "", f"{p.name} answered with something unexpected"
