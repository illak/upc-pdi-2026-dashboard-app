#!/usr/bin/env python3
"""Cliente mínimo Google API (Sheets/Drive) usando el token OAuth de ~/.hermes.

Uso:
    from gapi import token, api_get, sheets_values
"""
import json, time, urllib.parse, urllib.request, os

TOKEN_PATH = os.path.expanduser("~/.hermes/google_token.json")
_cache = {"tok": None, "exp": 0}


def token():
    if _cache["tok"] and time.time() < _cache["exp"] - 60:
        return _cache["tok"]
    with open(TOKEN_PATH) as f:
        t = json.load(f)
    body = urllib.parse.urlencode({
        "client_id": t["client_id"],
        "client_secret": t["client_secret"],
        "refresh_token": t["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(t["token_uri"], data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    _cache["tok"] = d["access_token"]
    _cache["exp"] = time.time() + int(d.get("expires_in", 3600))
    return _cache["tok"]


def api_get(url, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def sheets_values(sheet_id, rango="A1:Z", hoja=None):
    rng = f"{hoja}!{rango}" if hoja else rango
    rng = urllib.parse.quote(rng, safe="")
    return api_get(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{rng}")


def buscar_drive(q):
    return api_get("https://www.googleapis.com/drive/v3/files",
                   {"q": q, "fields": "files(id,name,mimeType,modifiedTime,webViewLink)",
                    "pageSize": 30, "orderBy": "modifiedTime desc"})


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "buscar":
        q = sys.argv[2] if len(sys.argv) > 2 else \
            "mimeType='application/vnd.google-apps.spreadsheet'"
        print(json.dumps(buscar_drive(q), ensure_ascii=False, indent=1))
    else:
        print("token OK:", token()[:12] + "...")