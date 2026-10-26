"""Zaległe leady: kto przyjął (albo mógł przyjąć) nasze zaproszenie, a listu nie dostał, bo w oknie nie starczyło normy.

Raz dziennie (z przebiegu Agenta, od 5:00) Analityczka pobiera z Kierownika surowe dane, odhacza wszystkich, którzy dostali list,
zostali ocenieni i odrzuceni, sami pisali albo już z nami rozmawiali — i z tego, co zostaje (luki), wybiera najstarsze zaproszenia.
Dzienną listę zanosi do Kierownika (POST /api/executor/zalegle); Kierownik pokazuje ją agentowi jako pierwszą przy listach.
Pominięcie „nie przyjął zaproszenia” nie skreśla osoby na zawsze: wraca po kilku dniach, najwyżej kilka razy.
"""
import json
import re
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import unquote

import requests

import nadzorca
import store

NOT_ACCEPTED = re.compile(r"2\.\s*stop|zaproszenie w toku|brak po[łl][aą]czenia|nie przyj[aą]|oczekuj|nie jest (?:w )?kontakt|"
                          r"nie ma (?:go |jej )?w kontaktach|pending|nie znaleziono w kontaktach", re.I)
MIN_DNI = 14         # ludzie przyjmują zaproszenia z opóźnieniem: wcześniej sprawdzanie to zbędny ruch na LinkedIn
MAX_DNI = 45         # starsze zaproszenia już nie są „stosunkowo nowe”
PRZERWA_DNI = 7      # po „nie przyjął” pytamy o osobę znowu dopiero po tylu dniach
MAX_PROB = 2         # po tylu „nie przyjął” osoba odpada (Kierownik i tak kasuje zaproszenia po 21 dniach)
GODZINA_OD = 5       # lista na dany dzień powstaje najwcześniej o tej godzinie
# niższy szczebel — list idzie tylko do decydentów, nawet jeśli zaproszenie poszło omyłkowo
NIZSZY_SZCZEBEL = re.compile(r"kierownik|manager|menedżer|menadżer|specjalist|inżynier|koordynator|supervisor|team leader|lider", re.I)


def _url(u: str | None) -> str:
    u = unquote((u or "").strip()).split("?")[0].split("#")[0].rstrip("/").lower()
    return re.sub(r"^https?://(www\.|pl\.)?", "", u)


def _nazwa(n: str | None) -> str:
    n = unicodedata.normalize("NFKD", (n or "").lower().replace("ł", "l"))
    return " ".join(re.sub(r"[^a-z ]+", "", "".join(ch for ch in n if not unicodedata.combining(ch))).split())


def ile_dziennie() -> int:
    try:
        return max(1, min(30, int(store.ustawienie("zalegle_ile", "10"))))
    except ValueError:
        return 10


def wylicz(d: dict, ile: int) -> dict:
    """Z surowych danych Kierownika: wszystkie luki (od najstarszego zaproszenia) i wybór na dziś."""
    teraz = datetime.strptime(d["teraz"][:19], "%Y-%m-%d %H:%M:%S")
    od, do = (teraz - timedelta(days=MAX_DNI)).strftime("%Y-%m-%d"), (teraz - timedelta(days=MIN_DNI)).strftime("%Y-%m-%d")
    przerwa = (teraz - timedelta(days=PRZERWA_DNI)).strftime("%Y-%m-%d %H:%M:%S")
    zalatwieni_u, zalatwieni_n = set(), set()

    def odhacz(r):
        if _url(r.get("profile_url")):
            zalatwieni_u.add(_url(r.get("profile_url")))
        if len(_nazwa(r.get("name"))) > 3:
            zalatwieni_n.add(_nazwa(r.get("name")))

    nie_przyjal: dict[str, list[str]] = {}
    for r in d.get("listy", []):
        if r["status"] == "pominieto" and NOT_ACCEPTED.search(r.get("reason") or ""):
            for k in (_url(r.get("profile_url")), _nazwa(r.get("name"))):
                if k:
                    nie_przyjal.setdefault(k, []).append(r.get("ts") or "")
        else:
            odhacz(r)                     # list wysłany albo osoba oceniona i odrzucona
    for klucz in ("w_zatwierdzaniu", "pisali", "rozmawialismy"):
        for r in d.get(klucz, []):
            odhacz(r)
    for t in store.teczki():              # kto ma teczkę, ten już z nami rozmawia
        odhacz({"profile_url": t.get("profil_url"), "name": t.get("nazwa")})

    luki, czeka = [], 0
    for r in d.get("zaproszenia", []):
        dzien = (r.get("ts") or "")[:10]
        if not (od <= dzien <= do):
            continue
        u, n = _url(r.get("profile_url")), _nazwa(r.get("name"))
        if u in zalatwieni_u or (n and n in zalatwieni_n):
            continue
        if NIZSZY_SZCZEBEL.search(r.get("headline") or ""):
            continue
        proby = sorted({ts[:10] for ts in nie_przyjal.get(u, []) + nie_przyjal.get(n, []) if ts})     # jeden dzień = jedna próba
        if len(proby) >= MAX_PROB:
            continue
        if proby and proby[-1] >= przerwa[:10]:
            czeka += 1                    # niedawno nie przyjął — zapytamy za kilka dni
            continue
        luki.append({"name": r.get("name") or "", "profile_url": r["profile_url"], "company": r.get("company") or "",
                     "headline": r.get("headline") or "", "invite_ts": r.get("ts") or "", "proby": len(proby),
                     "powod": f"zaproszenie {dzien}, brak listu" + (f"; wcześniej {len(proby)}× nie przyjął" if proby else "")})
    luki.sort(key=lambda x: (x["proby"], x["invite_ts"]))   # najpierw jeszcze niesprawdzani, wśród nich najstarsze zaproszenia
    return {"luk": len(luki), "czeka_na_przyjecie": czeka, "wybrane": luki[:ile]}


def przygotuj(wymus: bool = False) -> dict:
    """Raz dziennie: wylicz luki i zanieś Kierownikowi listę na dziś. `wymus` = od nowa, nawet gdy dziś już była."""
    teraz = datetime.now(store.TZ)
    dzis = teraz.strftime("%Y-%m-%d")
    if not wymus and (store.ustawienie("zalegle_dzien") == dzis or teraz.hour < GODZINA_OD):
        return {"ok": True, "pominieto": "dzisiejsza lista już jest albo za wcześnie"}
    if not nadzorca.TOKEN_KIER:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    h = {"X-Executor-Token": nadzorca.TOKEN_KIER}
    r = requests.get(f"{nadzorca.KIEROWNIK}/api/executor/zalegle-dane", headers=h, timeout=60)
    r.raise_for_status()
    w = wylicz(r.json(), ile_dziennie())
    r = requests.post(f"{nadzorca.KIEROWNIK}/api/executor/zalegle", headers=h, timeout=60,
                      json={"day": dzis, "leady": w["wybrane"]})
    r.raise_for_status()
    store.ustaw("zalegle_dzien", dzis)
    store.ustaw("zalegle_ostatnie", json.dumps({"dzien": dzis, "czas": store.teraz(), **w}, ensure_ascii=False))
    return {"ok": True, "dzien": dzis, "wyslano_do_kierownika": len(w["wybrane"]), "luk": w["luk"], "czeka_na_przyjecie": w["czeka_na_przyjecie"]}


def ostatnie() -> dict:
    try:
        return json.loads(store.ustawienie("zalegle_ostatnie", "") or "{}")
    except ValueError:
        return {}
