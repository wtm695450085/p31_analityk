"""Branże: szufladki „branża + rejon” (np. „Montownie — województwo łódzkie”).

Do szufladki właściciel wrzuca pliki z firmami (CSV, XLS, XLSX). Analityczka wyciąga z nich nazwy firm i zleca Detektywowi znalezienie
ich VIP-ów w LinkedIn; VIP-y wracają do szufladki, idą do Kierownika (zaproszenia wysyła agent GPT — wyłącznie zaproszenia),
a Analityczka pilnuje, ilu z nich jest już zaproszonych i ilu w kontaktach. Oferty do VIP-ów z szufladki pisze właściciel ręcznie.
"""
import csv
import io
import os
import re
import zipfile
from pathlib import Path

import requests

import store

KATALOG = store.DATA_DIR / "branze"
ROZSZERZENIA = (".csv", ".xls", ".xlsx")
MAX_BAJTOW = 25 * 1024 * 1024
PACZKA = 100                                       # tyle firm naraz przyjmuje Detektyw
DETEKTYW = os.getenv("DETEKTYW_URL", "http://detektyw:8000").rstrip("/")
DETEKTYW_TOKEN = os.getenv("DETEKTYW_TOKEN", "")
KIEROWNIK = os.getenv("KIEROWNIK_URL", "http://kierownik:8000").rstrip("/")
KIEROWNIK_TOKEN = os.getenv("KIEROWNIK_EXECUTOR_TOKEN", "")

KOL_FIRMA = ("nazwa firmy", "firma", "nazwa", "company", "nazwa podmiotu", "podmiot", "organizacja", "organization", "name")
KOL_MIASTO = ("miasto", "miejscowość", "miejscowosc", "city", "lokalizacja", "location")


def init():
    with store.conn() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS szuflady (id INTEGER PRIMARY KEY AUTOINCREMENT, branza TEXT NOT NULL, rejon TEXT NOT NULL DEFAULT '',
    utworzono TEXT NOT NULL, sync_ts TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS szuflada_firmy (id INTEGER PRIMARY KEY AUTOINCREMENT, szuflada_id INTEGER NOT NULL, firma TEXT NOT NULL,
    firma_lc TEXT NOT NULL, plik TEXT NOT NULL DEFAULT '', wyslano TEXT NOT NULL DEFAULT '', UNIQUE(szuflada_id, firma_lc));
CREATE TABLE IF NOT EXISTS szuflada_vipy (id INTEGER PRIMARY KEY AUTOINCREMENT, szuflada_id INTEGER NOT NULL, nazwa TEXT NOT NULL,
    firma TEXT NOT NULL DEFAULT '', stanowisko TEXT NOT NULL DEFAULT '', linkedin_url TEXT NOT NULL, dodano TEXT NOT NULL,
    zaproszony INTEGER NOT NULL DEFAULT 0, w_kontaktach INTEGER NOT NULL DEFAULT 0, UNIQUE(szuflada_id, linkedin_url));
""")
        for tab, col in (("szuflada_vipy", "odrzucony INTEGER NOT NULL DEFAULT 0"), ("szuflada_vipy", "powod TEXT NOT NULL DEFAULT ''"),
                         ("szuflada_vipy", "specjalny TEXT NOT NULL DEFAULT ''"), ("szuflada_vipy", "specjalny_powod TEXT NOT NULL DEFAULT ''"),
                         ("szuflady", "prompt_specjalny TEXT NOT NULL DEFAULT ''")):
            try:
                c.execute(f"ALTER TABLE {tab} ADD COLUMN {col}")
            except Exception:
                pass                                   # kolumna juz jest


def etykieta(s: dict) -> str:
    return s["branza"] + (f" — {s['rejon']}" if s["rejon"] else "")


# --------------------------------------------------------------- szufladki

def utworz(branza: str, rejon: str) -> int:
    branza, rejon = branza.strip()[:80], rejon.strip()[:80]
    if not branza:
        raise ValueError("Podaj nazwę branży")
    with store.conn() as c:
        r = next((x for x in c.execute("SELECT id, branza, rejon FROM szuflady") if x["branza"].lower() == branza.lower() and x["rejon"].lower() == rejon.lower()), None)
        if r:
            raise ValueError("Taka szufladka (branża + rejon) już istnieje")
        return c.execute("INSERT INTO szuflady(branza,rejon,utworzono) VALUES(?,?,?)", (branza, rejon, store.teraz())).lastrowid


def szuflada(sid: int) -> dict | None:
    with store.conn() as c:
        r = c.execute("SELECT * FROM szuflady WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def liczniki(sid: int) -> dict:
    with store.conn() as c:
        f = c.execute("SELECT COUNT(*) n, SUM(wyslano<>'') w FROM szuflada_firmy WHERE szuflada_id=?", (sid,)).fetchone()
        v = c.execute("SELECT COUNT(*) n, SUM(zaproszony) z, SUM(w_kontaktach) k, SUM(zaproszony=0 AND w_kontaktach=0 AND odrzucony=0) d, "
                      "SUM(odrzucony=1 AND w_kontaktach=0) o, SUM(w_kontaktach=1 AND specjalny='oczekuje') sp, SUM(specjalny<>'') ps "
                      "FROM szuflada_vipy WHERE szuflada_id=?", (sid,)).fetchone()
    return {"firm": f["n"] or 0, "firm_wyslanych": f["w"] or 0, "vipow": v["n"] or 0, "zaproszonych": v["z"] or 0,
            "w_kontaktach": v["k"] or 0, "do_zaproszenia": v["d"] or 0, "odrzuconych": v["o"] or 0, "specjalnych": v["sp"] or 0, "po_specjalnej": v["ps"] or 0}


def wszystkie() -> list[dict]:
    with store.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM szuflady ORDER BY id DESC")]
    return [{**s, **liczniki(s["id"])} for s in rows]


def usun_szuflade(sid: int):
    with store.conn() as c:
        for t in ("szuflada_vipy", "szuflada_firmy"):
            c.execute(f"DELETE FROM {t} WHERE szuflada_id=?", (sid,))
        c.execute("DELETE FROM szuflady WHERE id=?", (sid,))


def firmy(sid: int) -> list[dict]:
    with store.conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM szuflada_firmy WHERE szuflada_id=? ORDER BY id", (sid,))]


def vipy(sid: int, status: str = "") -> list[dict]:
    """status: "" wszyscy | kontakty (w kontaktach) | zaproszeni (zaproszeni, jeszcze nie w kontaktach) | do_zaproszenia"""
    warunek = {"kontakty": " AND w_kontaktach=1", "zaproszeni": " AND zaproszony=1 AND w_kontaktach=0",
               "do_zaproszenia": " AND zaproszony=0 AND w_kontaktach=0 AND odrzucony=0",
               "odrzuceni": " AND odrzucony=1 AND w_kontaktach=0", "po_specjalnej": " AND specjalny<>''"}.get(status, "")
    with store.conn() as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM szuflada_vipy WHERE szuflada_id=?{warunek} ORDER BY firma, nazwa", (sid,))]


# --------------------------------------------------------------- pliki z firmami

def _dekoduj(dane: bytes) -> str:
    for kodowanie in ("utf-8-sig", "cp1250"):
        try:
            return dane.decode(kodowanie)
        except UnicodeDecodeError:
            pass
    return dane.decode("utf-8", errors="replace")


def _wiersze(nazwa: str, dane: bytes) -> list[list[str]]:
    n = nazwa.lower()
    if n.endswith(".csv"):
        tekst = _dekoduj(dane)
        p = tekst[:4096]
        sep = ";" if p.count(";") > p.count(",") and p.count(";") >= p.count("\t") else ("\t" if p.count("\t") > p.count(",") else ",")
        return [[c.strip() for c in w] for w in csv.reader(io.StringIO(tekst), delimiter=sep)]
    if n.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(dane), read_only=True, data_only=True)
        return [["" if c is None else str(c).strip() for c in w] for w in wb.worksheets[0].iter_rows(values_only=True)]
    import xlrd
    ws = xlrd.open_workbook(file_contents=dane).sheet_by_index(0)
    return [[str(c).strip() if c not in (None, "") else "" for c in ws.row_values(i)] for i in range(ws.nrows)]


def wyciagnij_firmy(nazwa: str, dane: bytes) -> list[str]:
    """Nazwy firm z pliku. Kolumna firmy po nagłówku (firma, nazwa, company…), inaczej pierwsza kolumna; miasto (jeśli jest) dopisujemy po myślniku."""
    w = [r for r in _wiersze(nazwa, dane) if any(c for c in r)]
    if not w:
        return []
    naglowek = [c.lower() for c in w[0]]
    ifirma = next((i for k in KOL_FIRMA for i, h in enumerate(naglowek) if h == k), None)
    if ifirma is None:
        ifirma = next((i for k in KOL_FIRMA for i, h in enumerate(naglowek) if k in h), None)
    imiasto = next((i for k in KOL_MIASTO for i, h in enumerate(naglowek) if h == k), None)
    start = 1 if ifirma is not None else 0                       # bez rozpoznanego naglowka bierzemy pierwsza kolumne i nic nie gubimy
    if ifirma is None:
        ifirma = 0
        start = 1 if len(w) > 1 and re.fullmatch(r"(?i)\s*(lp\.?|nr|id|nazwa|firma|company)\s*", w[0][0] or "") else 0
    out, widziane = [], set()
    for r in w[start:]:
        f = (r[ifirma] if ifirma < len(r) else "").strip()
        if len(f) < 2 or f.lower() in widziane:
            continue
        widziane.add(f.lower())
        m = (r[imiasto].strip() if imiasto is not None and imiasto < len(r) else "")
        out.append(f"{f} — {m}" if m and m.lower() not in f.lower() else f)
    return out


def wrzuc(sid: int, nazwa: str, dane: bytes) -> int:
    """Zapisuje plik w katalogu szufladki i dodaje jej nowe firmy. Zwraca liczbę NOWYCH firm; ValueError z komunikatem, gdy plik nie pasuje."""
    n = re.sub(r"[^\w.\- ()]+", "_", Path((nazwa or "").replace("\\", "/")).name, flags=re.U).strip(" .")[:150]
    if not n.lower().endswith(ROZSZERZENIA):
        raise ValueError(f"„{nazwa or 'bez nazwy'}”: dozwolone tylko pliki CSV, XLS i XLSX")
    if not dane or len(dane) > MAX_BAJTOW:
        raise ValueError(f"„{n}”: plik jest pusty albo większy niż {MAX_BAJTOW // 1024 // 1024} MB")
    try:
        nazwy = wyciagnij_firmy(n, dane)
    except Exception as e:
        raise ValueError(f"„{n}”: nie udało się odczytać pliku ({type(e).__name__})")
    if not nazwy:
        raise ValueError(f"„{n}”: nie znalazłem w pliku żadnych firm")
    katalog = KATALOG / str(sid)
    katalog.mkdir(parents=True, exist_ok=True)
    cel, i = katalog / n, 1
    while cel.exists():
        cel = katalog / f"{Path(n).stem} ({i}){Path(n).suffix}"
        i += 1
    cel.write_bytes(dane)
    nowe = 0
    with store.conn() as c:
        for f in nazwy:
            nowe += c.execute("INSERT OR IGNORE INTO szuflada_firmy(szuflada_id,firma,firma_lc,plik) VALUES(?,?,?,?)",
                              (sid, f[:150], f[:150].lower(), cel.name)).rowcount
    return nowe


# --------------------------------------------------------------- Detektyw i Kierownik

def zlec_detektywowi(sid: int) -> dict:
    """Wysyla Detektywowi firmy, ktorych jeszcze nie wyslano (paczkami po 100). Detektyw szuka sam i odsyla VIP-ow przez /api/detektyw/vipy."""
    if not DETEKTYW_TOKEN:
        raise RuntimeError("Brak DETEKTYW_TOKEN w .env")
    czekajace = [f for f in firmy(sid) if not f["wyslano"]]
    if not czekajace:
        return {"wyslano": 0, "uwaga": "Wszystkie firmy z tej szufladki już zlecono Detektywowi."}
    wyslano = 0
    for i in range(0, len(czekajace), PACZKA):
        paczka = czekajace[i:i + PACZKA]
        r = requests.post(f"{DETEKTYW}/api/analityk/zlecenie-firm", json={"szuflada": sid, "firmy": [f["firma"] for f in paczka]},
                          headers={"X-Detektyw-Token": DETEKTYW_TOKEN}, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"Detektyw odpowiedział {r.status_code}: {r.text[:160]}")
        with store.conn() as c:
            c.executemany("UPDATE szuflada_firmy SET wyslano=? WHERE id=?", [(store.teraz(), f["id"]) for f in paczka])
        wyslano += len(paczka)
    return {"wyslano": wyslano, "uwaga": ""}


def stan_detektywa(sid: int) -> dict | None:
    try:
        r = requests.get(f"{DETEKTYW}/api/analityk/szuflada/{sid}", headers={"X-Detektyw-Token": DETEKTYW_TOKEN}, timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def zapisz_vipa(sid: int, v: dict) -> bool:
    """VIP od Detektywa trafia do szufladki (ten sam adres LinkedIn tylko raz)."""
    if not szuflada(sid):
        return False
    with store.conn() as c:
        return bool(c.execute("INSERT OR IGNORE INTO szuflada_vipy(szuflada_id,nazwa,firma,stanowisko,linkedin_url,dodano) VALUES(?,?,?,?,?,?)",
                              (sid, v["nazwa"], v.get("firma") or "", v.get("stanowisko") or "", v["linkedin_url"], store.teraz())).rowcount)


def odswiez_statusy(sid: int) -> dict:
    """Pyta Kierownika, kogo z VIP-ow szufladki zaproszono i kto jest w kontaktach."""
    lista = vipy(sid)
    if not lista:
        return {"ok": True, "sprawdzono": 0}
    if not KIEROWNIK_TOKEN:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    r = requests.post(f"{KIEROWNIK}/api/executor/vip-status", json={"urls": [v["linkedin_url"] for v in lista], "prompt": (szuflada(sid) or {}).get("prompt_specjalny") or ""},
                      headers={"X-Executor-Token": KIEROWNIK_TOKEN}, timeout=60)
    r.raise_for_status()
    st = r.json().get("status") or {}
    with store.conn() as c:
        for v in lista:
            s = st.get(v["linkedin_url"]) or {}
            c.execute("UPDATE szuflada_vipy SET zaproszony=?, w_kontaktach=?, odrzucony=?, powod=?, specjalny=?, specjalny_powod=? WHERE id=?",
                      (int(bool(s.get("zaproszony") or s.get("w_kontaktach"))), int(bool(s.get("w_kontaktach"))),
                       int(bool(s.get("odrzucony")) and not s.get("w_kontaktach")), str(s.get("powod") or "")[:300],
                       str(s.get("specjalny") or ""), str(s.get("specjalny_powod") or "")[:300], v["id"]))
        c.execute("UPDATE szuflady SET sync_ts=? WHERE id=?", (store.teraz(), sid))
    return {"ok": True, "sprawdzono": len(lista)}


def odswiez_wszystkie():
    """Wolane z petli Agenta: statusy wszystkich szufladek (Analityczka sama pilnuje, ilu jest zaproszonych i w kontaktach)."""
    for s in wszystkie():
        if s["vipow"]:
            try:
                odswiez_statusy(s["id"])
            except Exception:
                pass


def zapisz_prompt_specjalny(sid: int, prompt: str):
    with store.conn() as c:
        c.execute("UPDATE szuflady SET prompt_specjalny=? WHERE id=?", (prompt.strip(), sid))


def wyslij_specjalnie(sid: int, ids: list[int]) -> dict:
    """Wlasciciel klika „Wyslij specjalna procedura”: wybrani VIP-y, ktorzy sa juz w kontaktach, ida do Kierownika razem z promptem szufladki.
    Agent GPT dostaje je na stronie wizyty w osobnej karcie; automat nigdy nie pisze do VIP-ow z szufladek."""
    s = szuflada(sid)
    prompt = (s["prompt_specjalny"] or "").strip()
    if not prompt:
        raise ValueError("Wpisz prompt specjalnej procedury (jak ma wyglądać wiadomość do tych osób) i zapisz go")
    wybrani = [v for v in vipy(sid, "kontakty") if v["id"] in set(ids)]
    if not wybrani:
        raise ValueError("Zaznacz osoby z zakładki „już w kontaktach”")
    if not KIEROWNIK_TOKEN:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    r = requests.post(f"{KIEROWNIK}/api/executor/vip-special", timeout=60, headers={"X-Executor-Token": KIEROWNIK_TOKEN},
                      json={"prompt": prompt, "szuflada": etykieta(s), "vips": [
                          {"nazwa": v["nazwa"], "firma": v["firma"], "stanowisko": v["stanowisko"], "linkedin_url": v["linkedin_url"]} for v in wybrani]})
    r.raise_for_status()
    dup = {str(u).split("?")[0].rstrip("/").lower() for u in (r.json().get("duplikaty") or [])}
    with store.conn() as c:
        for v in wybrani:
            if v["linkedin_url"].split("?")[0].rstrip("/").lower() in dup:     # ten sam list specjalny poszedł już z innej szufladki
                c.execute("UPDATE szuflada_vipy SET specjalny='wyslano', specjalny_powod='już dostał ten list (inna szufladka)' WHERE id=?", (v["id"],))
            else:
                c.execute("UPDATE szuflada_vipy SET specjalny='oczekuje', specjalny_powod='' WHERE id=?", (v["id"],))
    return {"ok": True, "wyslano": len(wybrani) - len(dup), "duplikaty": len(dup)}
