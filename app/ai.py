"""OpenAI dla Analityka: lista modeli do wyboru i analiza leada (opcjonalnie z wyszukiwaniem w sieci)."""
import json
import os
import re
import threading
import time

import requests

BAZA = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "240"))
MODEL_DOMYSLNY = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
SDK_MODELE = ["gpt-6-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]      # modele Codexa (abonament)
ZALECANE = ["gpt-5.4-mini", "gpt-5.4", "gpt-5.5", "gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"]
ODRZUC = re.compile(r"(audio|realtime|image|tts|transcribe|whisper|embedding|moderation|dall|sora|live|diarize|instruct|deep-research|search)", re.I)
_cache = {"t": 0.0, "m": []}
_zamek = threading.Lock()


def klucz() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def wlaczone() -> bool:
    return sdk_gotowy() if silnik() == "sdk" else bool(klucz())


# --------------------------------------------------------------- silnik: API (klucz OpenAI) albo SDK (abonament ChatGPT przez Codex)

def silnik() -> str:
    import store
    return "sdk" if store.ustawienie("silnik", "api") == "sdk" else "api"


def model_sdk() -> str:
    import store
    return store.ustawienie("model_sdk", "")        # pusty = domyslny model Codexa


def sdk_gotowy() -> bool:
    return bool(os.getenv("CODEX_BRIDGE_URL") and os.getenv("CODEX_BRIDGE_TOKEN"))


def sdk_uruchom(instrukcja: str, wejscie: str, szukaj: bool, timeout: float = 0, model: str = "") -> str:
    """Pytanie do modelu z abonamentu ChatGPT: most na hoscie uruchamia `codex exec` (dane logowania zostaja na hoscie)."""
    if not sdk_gotowy():
        raise RuntimeError("Brak CODEX_BRIDGE_URL / CODEX_BRIDGE_TOKEN w .env")
    t = timeout or TIMEOUT
    r = requests.post(os.environ["CODEX_BRIDGE_URL"].rstrip("/") + "/v1/run", timeout=t + 30,
                      headers={"X-Bridge-Token": os.environ["CODEX_BRIDGE_TOKEN"]},
                      json={"instructions": instrukcja, "input": wejscie, "web_search": szukaj,
                            "model": model or model_sdk(), "timeout": int(t)})
    if r.status_code >= 400:
        raise RuntimeError(f"SDK (abonament) {r.status_code}: {r.text[:300]}")
    return r.json().get("text", "")


def modele(odswiez: bool = False) -> list[str]:
    with _zamek:
        if not odswiez and _cache["m"] and time.time() - _cache["t"] < 3600:
            return list(_cache["m"])
    if silnik() == "sdk" or not klucz():          # SDK: bez zapytan do API OpenAI, lista modeli tylko z kodu
        return list(ZALECANE)
    try:
        r = requests.get(f"{BAZA}/models", timeout=30, headers={"Authorization": f"Bearer {klucz()}"})
        r.raise_for_status()
        wszystkie = [m["id"] for m in r.json().get("data", [])]
    except Exception:
        return list(ZALECANE)
    ok = sorted(m for m in wszystkie if m.startswith(("gpt-", "o1", "o3", "o4")) and not ODRZUC.search(m))
    lista = [m for m in ZALECANE if m in ok] + [m for m in ok if m not in ZALECANE]
    with _zamek:
        _cache.update({"t": time.time(), "m": lista})
    return lista


def wyluskaj_json(tekst: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", (tekst or "").strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise RuntimeError(f"odpowiedź bez JSON-a: {tekst[:200]}")
    return json.loads(t[a:b + 1])


def zapytaj(model: str, instrukcja: str, wejscie: str, szukaj_w_sieci: bool, rozumowanie: str = "", model_sdk_zadania: str = "", timeout: float = 0,
            silnik_zadania: str = "") -> str:
    """API Responses; z narzedziem web_search model sam sprawdza osobe i firme w internecie. `silnik_zadania` (api/sdk) — wlasny silnik agenta zamiast wspolnego."""
    if (silnik_zadania or silnik()) == "sdk":
        return sdk_uruchom(instrukcja, wejscie, szukaj_w_sieci, timeout=timeout, model=model_sdk_zadania)
    body = {"model": model, "instructions": instrukcja, "input": wejscie}
    if szukaj_w_sieci:
        body["tools"] = [{"type": "web_search"}]
    if rozumowanie and model.startswith(("gpt-5", "o1", "o3", "o4")):
        body["reasoning"] = {"effort": rozumowanie}                     # glebsze myslenie do odprawy strategicznej
    r = requests.post(f"{BAZA}/responses", timeout=timeout or TIMEOUT, json=body,
                      headers={"Authorization": f"Bearer {klucz()}", "Content-Type": "application/json"})
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    tekst = []
    for o in r.json().get("output", []):
        if o.get("type") == "message":
            tekst += [c.get("text", "") for c in o.get("content", []) if c.get("type") == "output_text"]
    return "\n".join(tekst)
