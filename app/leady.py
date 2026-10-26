"""Leady do listów: drugi agent Analityczki. W nocy przegląda bazę kontaktów Kierownika (Connections.csv) od najnowszych,
wybranym modelem ocenia stanowisko i firmę i dokłada zakwalifikowanych do kolejki listów w Kierowniku — bez wchodzenia na LinkedIn.

Kierownik sam odsiewa tych, którzy dostali list, byli oceniani przy listach, sami pisali albo już są w kolejce.
Tu odpadają jeszcze osoby z teczką i te, które agent już kiedyś ocenił (oceny są zapamiętane — nikt nie jest oceniany dwa razy).
Agent dobija kolejkę do zadanej liczby czekających i pracuje najwyżej `leady_minuty` minut na przebieg.
"""
import json
import logging
import re
import threading
import time
from datetime import datetime

import requests

import ai
import nadzorca
import store
from zalegle import _nazwa, _url

log = logging.getLogger("leady")
_zamek = threading.Lock()

PROMPT_DOMYSLNY = """Jesteś analitykiem sprzedaży Wojciecha Moszczyńskiego (wdrożenia AI w firmach produkcyjnych, dedykowane aplikacje: kontrola produkcji, koszty i marża, wizja komputerowa, prognozy).
Dostajesz porcję jego kontaktów z LinkedIn: imię i nazwisko, stanowisko, firma. Wybierz osoby, do których warto wysłać list sprzedażowy.

Wybierz TYLKO osoby, które spełniają WSZYSTKIE trzy warunki naraz. Jakość ważniejsza niż ilość — lepiej zwrócić 3 dobre osoby niż 30 przypadkowych.

WARUNEK 1 — POLAK (kraj=PL). Osoba działa w Polsce: polskie imię i nazwisko ORAZ polska firma (np. „Sp. z o.o.”, „S.A.”, polska nazwa, polskie stanowisko, polski oddział). Cudzoziemcy, firmy zagraniczne, nazwiska zagraniczne, nazwy z „Ltd”, „GmbH”, „LLC”, „Inc”, wpisy wyłącznie po angielsku w zagranicznej firmie, pismo niełacińskie, globalne korporacje — kraj=inny. Gdy nie masz pewności — kraj=nieznany. Do listów kwalifikuje się tylko kraj=PL.

WARUNEK 2 — DECYDENT. Dokładnie te role: właściciel, współwłaściciel, założyciel (prowadzący firmę), prezes, wiceprezes, CEO, członek zarządu, dyrektor zarządzający, dyrektor generalny, dyrektor finansowy (CFO), dyrektor produkcji, dyrektor operacyjny/zakładu, kierownik produkcji / szef produkcji / kierownik zakładu.
NIE kwalifikuj: kierowników projektów, IT, jakości, logistyki, utrzymania ruchu, marketingu, sprzedaży, kontrolerów, księgowych, specjalistów, analityków, head-of w korporacjach, członków rad nadzorczych, partnerów funduszy.

WARUNEK 3 — FIRMA PRODUKCYJNA. Z nazwy firmy albo stanowiska musi WYRAŹNIE wynikać, że firma coś wytwarza (zakład, fabryka, producent: tworzywa, metal, meble, opakowania, elektronika, maszyny, spożywcza, chemia, drewno, druk, wyroby budowlane itp.). Gdy branża jest niejasna, nieznana albo „samozatrudnienie” / jednoosobowa działalność / „Business Owner” bez nazwy firmy — produkcja=niejasna i NIE kwalifikujesz.

ZAWSZE ODRZUĆ: rekruterzy, HR, headhunterzy i firmy rekrutacyjne (także gdy to prezes takiej firmy); marketing, reklama, PR, sprzedaż, handlowcy; konsultanci, doradcy, trenerzy, coachowie, freelancerzy; IT i software house'y, startupy technologiczne; finanse, banki, ubezpieczenia, nieruchomości, edukacja, urzędy, fundacje, handel, dystrybucja, transport, logistyka, usługi, energetyka; studenci, szukający pracy."""

FORMAT = """
Odpowiedz WYŁĄCZNIE JSON-em: {"wyniki": [{"i": <numer z wejścia>, "kraj": "PL"|"inny"|"nieznany", "rola": "decydent"|"inna", "produkcja": "tak"|"nie"|"niejasna", "ok": true|false, "powod": "<3–8 słów: dlaczego>"}]} — po jednym wpisie dla KAŻDEJ osoby z wejścia. ok=true TYLKO gdy kraj=PL i rola=decydent i produkcja=tak."""

# twarde odrzucenia w kodzie — niezależnie od odpowiedzi modelu (rekruterzy, marketing, sprzedaż, doradcy, IT, samozatrudnieni)
ODRZUC_RE = re.compile(
    r"rekrut|recruit|headhunt|talent|staffing|\bhr\b|human resources|kadr|marketing|reklam|\bpr\b|public relations|social media|"
    r"sprzeda|\bsales\b|handlow|business development|account manager|konsult|consult|doradc|advis|coach|trener|trainer|freelanc|"
    r"samozatrudn|self[- ]employed|student|praktykant|open to work|szukam pracy|"
    r"software|\bit\b|\bai\b|digital|cyber|agencj|agency|bank|ubezpiecz|insurance|nieruchomo|real estate|fundacj|"
    r"rada nadzorcza|supervisory board|partner|specjalist|specialist|analityk|analyst|asystent|assistant", re.I)


def odrzucony_kodem(k: dict) -> str:
    """Pusty napis = można oceniać modelem; w przeciwnym razie powód twardego odrzucenia."""
    tekst = f"{k.get('position') or ''} {k.get('company') or ''}"
    m = ODRZUC_RE.search(tekst)
    if m:
        return f"odrzucone: „{m.group(0).strip()}” w stanowisku/firmie"
    if not (k.get("company") or "").strip() or not (k.get("position") or "").strip():
        return "odrzucone: brak firmy lub stanowiska"
    return ""


def ustawienia() -> dict:
    def liczba(k, d, lo, hi):
        try:
            return max(lo, min(hi, int(store.ustawienie(k, str(d)))))
        except ValueError:
            return d
    return {"silnik": "sdk" if store.ustawienie("leady_silnik", ai.silnik()) == "sdk" else "api",
            "model": store.ustawienie("leady_model", ai.MODEL_DOMYSLNY),
            "model_sdk": store.ustawienie("leady_model_sdk", ""),
            "cel": liczba("leady_cel", 150, 1, 2000), "prog": liczba("leady_prog", 60, 0, 2000), "minuty": liczba("leady_minuty", 40, 1, 180),
            "porcja": liczba("leady_porcja", 40, 5, 100), "godzina": liczba("leady_godzina", 1, 0, 23),
            "prompt": store.ustawienie("leady_prompt", "") or PROMPT_DOMYSLNY}


def init():
    with store.conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS leady_oceny (url TEXT PRIMARY KEY, nazwa TEXT NOT NULL DEFAULT '', stanowisko TEXT NOT NULL DEFAULT '', "
                  "firma TEXT NOT NULL DEFAULT '', ok INTEGER NOT NULL DEFAULT 0, powod TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', kiedy TEXT NOT NULL)")


def _ocenieni() -> set:
    with store.conn() as c:
        return {r["url"] for r in c.execute("SELECT url FROM leady_oceny")}


def _zapisz_oceny(oceny: list[dict], model: str):
    teraz = store.teraz()
    with store.conn() as c:
        for o in oceny:
            c.execute("INSERT INTO leady_oceny(url,nazwa,stanowisko,firma,ok,powod,model,kiedy) VALUES(?,?,?,?,?,?,?,?) "
                      "ON CONFLICT(url) DO UPDATE SET ok=excluded.ok, powod=excluded.powod, model=excluded.model, kiedy=excluded.kiedy",
                      (o["url"], o["name"], o["position"], o["company"], int(o["ok"]), o["powod"][:200], model, teraz))


def liczniki_ocen() -> dict:
    init()
    with store.conn() as c:
        r = c.execute("SELECT COUNT(*) n, COALESCE(SUM(ok),0) ok FROM leady_oceny").fetchone()
    return {"ocenionych": r["n"], "zakwalifikowanych": r["ok"]}


def _ocen(porcja: list[dict], u: dict) -> list[dict]:
    wejscie = json.dumps([{"i": i, "nazwa": k["name"], "stanowisko": k["position"], "firma": k["company"]} for i, k in enumerate(porcja)], ensure_ascii=False)
    tekst = ai.zapytaj(u["model"], u["prompt"] + FORMAT, wejscie, False, model_sdk_zadania=u["model_sdk"], timeout=300, silnik_zadania=u["silnik"])
    wyniki = {int(w["i"]): w for w in ai.wyluskaj_json(tekst).get("wyniki", []) if str(w.get("i", "")).isdigit()}
    out = []
    for i, k in enumerate(porcja):
        if i in wyniki:                          # bez odpowiedzi modelu osoba nie jest oceniona — wróci w kolejnym przebiegu
            w = wyniki[i]
            # kwalifikacja tylko gdy model potwierdził WSZYSTKIE trzy warunki (kraj PL, decydent, produkcja) — samo ok=true nie wystarcza
            ok = bool(w.get("ok")) and str(w.get("kraj", "")).upper() == "PL" and w.get("rola") == "decydent" and w.get("produkcja") == "tak"
            powod = str(w.get("powod") or "")
            if w.get("ok") and not ok:
                powod = f"odrzucone: kraj={w.get('kraj')}, rola={w.get('rola')}, produkcja={w.get('produkcja')}"
            out.append({**k, "url": _url(k["profile_url"]), "ok": ok, "powod": powod})
    return out


def przygotuj(zrodlo: str = "ręcznie") -> dict:
    """Jeden przebieg: dobij kolejkę listów w Kierowniku do `cel` czekających, najwyżej `minuty` minut."""
    if not _zamek.acquire(blocking=False):
        return {"ok": False, "pominieto": "przebieg już trwa"}
    start, u = time.monotonic(), ustawienia()
    wynik = {"czas": store.teraz(), "zrodlo": zrodlo, "model": (u["model_sdk"] or "SDK domyślny") if u["silnik"] == "sdk" else u["model"],
             "ocenionych": 0, "dodanych": 0, "bledow": 0, "czeka_przed": 0, "czeka_po": 0, "kandydatow": 0, "uwaga": ""}
    try:
        init()
        if u["silnik"] == "api" and not ai.klucz():
            raise RuntimeError("Brak OPENAI_API_KEY")
        if u["silnik"] == "sdk" and not ai.sdk_gotowy():
            raise RuntimeError("Brak CODEX_BRIDGE_URL / CODEX_BRIDGE_TOKEN w .env")
        h = {"X-Executor-Token": nadzorca.TOKEN_KIER}
        r = requests.get(f"{nadzorca.KIEROWNIK}/api/executor/leady-dane", headers=h, timeout=120)
        r.raise_for_status()
        d = r.json()
        wynik["czeka_przed"] = wynik["czeka_po"] = d.get("czeka", 0)
        if zrodlo == "auto" and d.get("czeka", 0) >= u["prog"]:
            wynik["pusty"] = True                # przebieg automatyczny bez pracy — nie nadpisuje zapisu ostatniego prawdziwego przebiegu
            return wynik
        brak = u["cel"] - d.get("czeka", 0)
        if brak <= 0:
            wynik["uwaga"] = f"W kolejce czeka już {d.get('czeka', 0)} (cel {u['cel']}) — nic nie dokładam."
            return wynik
        ocenieni = _ocenieni()
        teczki_u, teczki_n = set(), set()
        for t in store.teczki():                 # kto ma teczkę, ten już z nami rozmawia
            teczki_u.add(_url(t.get("profil_url")))
            teczki_n.add(_nazwa(t.get("nazwa")))
        kand = [k for k in d.get("kandydaci", []) if _url(k["profile_url"]) not in ocenieni
                and _url(k["profile_url"]) not in teczki_u and _nazwa(k["name"]) not in teczki_n]
        wynik["kandydatow"] = len(kand)
        bledy_pod_rzad = 0
        for i in range(0, len(kand), u["porcja"]):
            if wynik["dodanych"] >= brak:
                break
            if time.monotonic() - start > u["minuty"] * 60:
                wynik["uwaga"] = f"Koniec czasu ({u['minuty']} min)."
                break
            porcja, twarde = [], []
            for k in kand[i:i + u["porcja"]]:
                p = odrzucony_kodem(k)               # rekruterzy, marketing, sprzedaż, doradcy itd. odpadają bez pytania modelu
                if p:
                    twarde.append({**k, "url": _url(k["profile_url"]), "ok": False, "powod": p})
                else:
                    porcja.append(k)
            if twarde:
                _zapisz_oceny(twarde, "filtr")
                wynik["ocenionych"] += len(twarde)
            if not porcja:
                continue
            try:
                oceny = _ocen(porcja, u)
                bledy_pod_rzad = 0
            except Exception as e:
                wynik["bledow"] += 1
                bledy_pod_rzad += 1
                wynik["uwaga"] = f"Błąd modelu: {type(e).__name__}: {str(e)[:160]}"
                log.warning("leady: %s", wynik["uwaga"])
                if bledy_pod_rzad >= 3:
                    break
                continue
            _zapisz_oceny(oceny, wynik["model"])
            wynik["ocenionych"] += len(oceny)
            dobre = [o for o in oceny if o["ok"]][:brak - wynik["dodanych"]]
            if dobre:
                r = requests.post(f"{nadzorca.KIEROWNIK}/api/executor/leady", headers=h, timeout=60, json={
                    "model": wynik["model"], "leady": [{"name": o["name"], "profile_url": o["profile_url"], "company": o["company"],
                                                       "position": o["position"], "connected_on": o["connected_on"], "powod": o["powod"]} for o in dobre]})
                r.raise_for_status()
                wynik["dodanych"] += r.json().get("dodano", 0)
                wynik["czeka_po"] = r.json().get("czeka", wynik["czeka_po"])
        else:
            if wynik["dodanych"] < brak and not wynik["uwaga"]:
                wynik["uwaga"] = "BRAK NOWYCH KONTAKTÓW DO OCENY — wszystkie z bazy Kierownika są już ocenione. Nowych leadów nie będzie, dopóki nie wgrasz świeżego Connections.csv do Kierownika. Do tego czasu Agent GPT działa na procedurze rezerwowej (Moja sieć → Kontakty od najnowszych)."
        return wynik
    except Exception as e:
        wynik["uwaga"] = f"{type(e).__name__}: {str(e)[:200]}"
        return wynik
    finally:
        wynik["minut"] = round((time.monotonic() - start) / 60, 1)
        if not wynik.get("pusty"):
            store.ustaw("leady_ostatni", json.dumps(wynik, ensure_ascii=False))
        _zamek.release()


def w_nocy() -> str:
    """Z przebiegu Agenta (co 30 min): o każdej porze, gdy kolejka listów spadnie poniżej `leady_prog`, uzupełnia ją w tle do `leady_cel`
    (przebieg trwa do `minuty` minut). Kolejka nie może się wyczerpać — Agent GPT ma zawsze mieć komu wysłać list."""
    if _zamek.locked():
        return "trwa"
    threading.Thread(target=przygotuj, args=("auto",), daemon=True).start()
    return "start"


def uruchom_teraz() -> bool:
    if _zamek.locked():
        return False
    threading.Thread(target=przygotuj, args=("ręcznie",), daemon=True).start()
    return True


def ostatni() -> dict:
    try:
        return json.loads(store.ustawienie("leady_ostatni", "") or "{}")
    except ValueError:
        return {}


def kolejka(limit: int = 300) -> dict:
    """Podgląd kolejki w Kierowniku (kto czeka po kolei, kto ostatnio zszedł)."""
    try:
        r = requests.get(f"{nadzorca.KIEROWNIK}/api/executor/leady-kolejka", params={"limit": limit},
                         headers={"X-Executor-Token": nadzorca.TOKEN_KIER}, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"blad": f"{type(e).__name__}: {str(e)[:120]}"}
