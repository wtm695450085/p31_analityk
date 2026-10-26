"""SQLite Analityka: teczki osob, ich wiadomosci (od leada i od nas), ustawienia i przebiegi agent_Darwin."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

DATA_DIR = Path(os.getenv("DATA_DIR", "/srv/data"))
DB_PATH = DATA_DIR / "analityk.db"
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Warsaw"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS teczki (
    id INTEGER PRIMARY KEY AUTOINCREMENT, klucz TEXT UNIQUE NOT NULL, nazwa TEXT NOT NULL, profil_url TEXT NOT NULL DEFAULT '',
    naglowek TEXT NOT NULL DEFAULT '', utworzono TEXT NOT NULL, ostatnia_wiadomosc TEXT NOT NULL DEFAULT '',
    do_oceny INTEGER NOT NULL DEFAULT 1,
    pozytywna INTEGER NOT NULL DEFAULT 0, rodzaj TEXT NOT NULL DEFAULT '', termin TEXT NOT NULL DEFAULT '',
    streszczenie TEXT NOT NULL DEFAULT '', nastepny_krok TEXT NOT NULL DEFAULT '', ocena INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '', ocenione TEXT NOT NULL DEFAULT '', blad TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS wiadomosci (
    id INTEGER PRIMARY KEY AUTOINCREMENT, teczka_id INTEGER NOT NULL, hash TEXT UNIQUE NOT NULL,
    kierunek TEXT NOT NULL, rodzaj TEXT NOT NULL DEFAULT '', kiedy TEXT NOT NULL DEFAULT '', tekst TEXT NOT NULL,
    zaimportowano TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_wiad_teczka ON wiadomosci(teczka_id, id);
CREATE TABLE IF NOT EXISTS poczta (
    id INTEGER PRIMARY KEY, nadawca TEXT NOT NULL DEFAULT '', temat TEXT NOT NULL DEFAULT '', kiedy TEXT NOT NULL DEFAULT '',
    tresc TEXT NOT NULL DEFAULT '', projekt TEXT NOT NULL DEFAULT '', ocenione INTEGER NOT NULL DEFAULT 0,
    zaimportowano TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS detektyw_zlecenia (
    id INTEGER PRIMARY KEY AUTOINCREMENT, teczka_id INTEGER NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'oczekuje',
    utworzono TEXT NOT NULL, wynik TEXT NOT NULL DEFAULT '', zakonczono TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS skasowane (klucz TEXT PRIMARY KEY, nazwa TEXT NOT NULL DEFAULT '', kiedy TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS ustawienia (k TEXT PRIMARY KEY, v TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS aliasy (klucz TEXT PRIMARY KEY, teczka_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS odprawy (
    id INTEGER PRIMARY KEY AUTOINCREMENT, czas TEXT NOT NULL, zrodlo TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'trwa', postep TEXT NOT NULL DEFAULT '', wynik TEXT NOT NULL DEFAULT '', raporty TEXT NOT NULL DEFAULT '',
    blad TEXT NOT NULL DEFAULT '', zakonczono TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS zalecenia (
    id INTEGER PRIMARY KEY AUTOINCREMENT, teczka_id INTEGER NOT NULL, akcja TEXT NOT NULL, kiedy TEXT NOT NULL DEFAULT '',
    utworzono TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'otwarte', zamknieto TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_zal_teczka ON zalecenia(teczka_id, status);
CREATE TABLE IF NOT EXISTS przebiegi (
    id INTEGER PRIMARY KEY AUTOINCREMENT, czas TEXT NOT NULL, zrodlo TEXT NOT NULL,
    pobrano INTEGER NOT NULL DEFAULT 0, nowych_teczek INTEGER NOT NULL DEFAULT 0, nowych_wiadomosci INTEGER NOT NULL DEFAULT 0,
    ocenionych INTEGER NOT NULL DEFAULT 0, bledow INTEGER NOT NULL DEFAULT 0, uwaga TEXT NOT NULL DEFAULT '');
"""


def teraz() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
    init_projekty()
    with conn() as c:
        try:
            c.execute("ALTER TABLE detektyw_zlecenia ADD COLUMN tryb TEXT NOT NULL DEFAULT 'pelny'")
        except Exception:
            pass
    with conn() as c:
        for kol in ("firma TEXT NOT NULL DEFAULT ''", "stanowisko TEXT NOT NULL DEFAULT ''", "watek_url TEXT NOT NULL DEFAULT ''",
                    "wymuszona INTEGER NOT NULL DEFAULT 0", "smietnik INTEGER NOT NULL DEFAULT 0",
                    "ocena_reczna INTEGER", "miasto TEXT NOT NULL DEFAULT ''", "telefon TEXT NOT NULL DEFAULT ''",
                    "email TEXT NOT NULL DEFAULT ''", "www TEXT NOT NULL DEFAULT ''", "charakterystyka TEXT NOT NULL DEFAULT ''",
                    "odrzucona_ai INTEGER NOT NULL DEFAULT 0", "kolor TEXT NOT NULL DEFAULT ''",
                    "sektor TEXT NOT NULL DEFAULT ''", "vip INTEGER NOT NULL DEFAULT 0", "projekt_klucz TEXT NOT NULL DEFAULT ''",
                    "przejrzana INTEGER NOT NULL DEFAULT 0", "wysoka INTEGER NOT NULL DEFAULT 0", "telefon_brak INTEGER NOT NULL DEFAULT 0", "char_reczna INTEGER NOT NULL DEFAULT 0", "pilna TEXT NOT NULL DEFAULT ''",
                    "pilna_auto INTEGER NOT NULL DEFAULT 0", "wysoka_auto INTEGER NOT NULL DEFAULT 0", "wywiad_zaang INTEGER"):
            try:
                c.execute(f"ALTER TABLE teczki ADD COLUMN {kol}")
            except Exception:
                pass                                   # kolumna juz jest
        # Ocena Wywiadowcy („jak glosno mowi o AI”) to NIE zainteresowanie nami: lead bez zadnej korespondencji nie ma oceny cieplosci
        try:
            c.execute("UPDATE teczki SET wywiad_zaang=ocena_reczna, ocena_reczna=NULL WHERE ocena_reczna IS NOT NULL AND wywiad_zaang IS NULL "
                      "AND EXISTS(SELECT 1 FROM wiadomosci w WHERE w.teczka_id=teczki.id AND w.rodzaj='informacja' AND w.tekst LIKE 'Wywiadowca:%') "
                      "AND NOT EXISTS(SELECT 1 FROM wiadomosci w WHERE w.teczka_id=teczki.id AND w.ukryta=0 AND (w.kierunek='od_leada' OR w.wlasna=1 "
                      "OR (w.kierunek='od_nas' AND w.rodzaj IN ('list','zaproszenie','nasza odpowiedź'))))")
        except Exception:
            pass                                   # swieza baza: tabela wiadomosci jeszcze bez kolumn pomocniczych
        try:
            c.execute("ALTER TABLE wiadomosci ADD COLUMN ukryta INTEGER NOT NULL DEFAULT 0")       # wpis usuniety z widoku (hash zostaje, zeby import go nie przywrocil)
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE wiadomosci ADD COLUMN ts TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE wiadomosci ADD COLUMN wlasna INTEGER NOT NULL DEFAULT 0")      # wpis dopisany recznie przez wlasciciela
            c.execute("UPDATE wiadomosci SET wlasna=1 WHERE rodzaj IN ('wklejone','rozmowa telefoniczna','spotkanie','notatka','wiadomość LinkedIn')")
        except Exception:
            pass
        for r in c.execute("SELECT id, tekst, ts FROM wiadomosci WHERE rodzaj='wklejone'").fetchall():       # wpisy reczne: data zdarzenia z tekstu
            d = data_z_tekstu(r["tekst"])
            if d and r["ts"][:10] != d:
                c.execute("UPDATE wiadomosci SET ts=?, kiedy=? WHERE id=?", (d + " 12:00", d, r["id"]))
            if _RE_TELEFON_TXT.search(r["tekst"] or ""):
                c.execute("UPDATE wiadomosci SET rodzaj='rozmowa telefoniczna' WHERE id=?", (r["id"],))
        for r in c.execute("SELECT id, kiedy FROM wiadomosci WHERE ts='' AND kiedy<>''").fetchall():      # uzupelnij stare wpisy
            nowy = parse_ts(r["kiedy"])
            if nowy:
                c.execute("UPDATE wiadomosci SET ts=? WHERE id=?", (nowy, r["id"]))


# Teczki zakladamy tylko z korespondencji od tej daty. Starsze wchodza wylacznie przez Detektywa albo reczne zalozenie.
DATA_OD = os.getenv("DATA_OD", "2026-04-01")


def _stare(kiedy: str) -> bool:
    ts = parse_ts(kiedy)
    return bool(ts) and ts[:10] < DATA_OD


NIE_TECZKA = ("odmowa", "oferta_pracy", "rekrutacja", "automat")


def ustawienie(k: str, domyslne: str = "") -> str:
    with conn() as c:
        r = c.execute("SELECT v FROM ustawienia WHERE k=?", (k,)).fetchone()
    return r["v"] if r else domyslne


def ustaw(k: str, v: str):
    with conn() as c:
        c.execute("INSERT INTO ustawienia(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))


def parse_ts(kiedy: str) -> str:
    """Ujednolicony czas „RRRR-MM-DD GG:MM” (czas polski) albo pusty, gdy daty nie da sie odczytac
    (np. „poniedziałek 14:35” z listy LinkedIn)."""
    k = (kiedy or "").strip()
    if not k:
        return ""
    utc = k.upper().endswith("UTC")
    k = re.sub(r"\s*UTC$", "", k, flags=re.I)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            d = datetime.strptime(k[:19] if "T" in k or len(k) > 16 else k, fmt)
        except ValueError:
            continue
        if utc:
            d = d.replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
        return d.strftime("%Y-%m-%d %H:%M")
    return ""


_RE_DATA = re.compile(r"(\d{4}-\d{2}-\d{2})|(\d{1,2})[.](\d{1,2})[.](\d{4})")
_RE_TELEFON_TXT = re.compile(r"rozmow\w* telefon|telefoniczn|zadzwoni|dzwoni|dzwoniłe|rozmow\w* przez telefon", re.I)


def data_z_tekstu(tekst: str) -> str:
    """„…rozmowę dnia 2026-09-30…” -> 2026-09-30 (data zdarzenia, nie data wpisu). Pusty, gdy brak daty w tekscie."""
    m = _RE_DATA.search(tekst or "")
    if not m:
        return ""
    return m.group(1) or f"{int(m.group(4)):04d}-{int(m.group(3)):02d}-{int(m.group(2)):02d}"


def klucz_osoby(profil_url: str, nazwa: str) -> str:
    u = unquote((profil_url or "").strip()).split("?")[0].split("#")[0].rstrip("/").lower()
    u = re.sub(r"^https?://(www\.|pl\.)?", "", u)
    return u or " ".join((nazwa or "").lower().split())


def _hash(*cz) -> str:
    return hashlib.sha1("|".join(str(x) for x in cz).encode()).hexdigest()


def _skasowana(c, klucz: str, nazwa: str) -> bool:
    """Teczka skasowana przez wlasciciela nie wraca z automatycznych importow (wraca tylko po jawnym dodaniu)."""
    return bool(c.execute("SELECT 1 FROM skasowane WHERE klucz=? OR (nazwa<>'' AND nazwa=?)", (klucz, (nazwa or "").lower())).fetchone())


def przyjmij(o: dict) -> tuple[bool, int]:
    """Zaklada teczke (jesli jej nie ma) i dopisuje wiadomosci. Zwraca (nowa_teczka, nowych_wiadomosci)."""
    o = {**o, "profile_url": o.get("profile_url") or "", "headline": o.get("headline") or "", "name": o.get("name") or ""}
    nazwa = o["name"].strip()
    klucz = klucz_osoby(o["profile_url"], nazwa)
    if not klucz or not (o.get("text") or "").strip():
        return False, 0
    if _stare(o.get("received") or o.get("reported_at") or ""):
        return False, 0                           # korespondencja sprzed DATA_OD nie zaklada teczki ani sie nie dopisuje
    nowa, dodane = False, 0
    with conn() as c:
        if _skasowana(c, klucz, nazwa):
            return False, 0
        t = c.execute("SELECT id FROM teczki WHERE klucz=?", (klucz,)).fetchone() or _alias(c, klucz)
        if not t and nazwa:
            # Ta sama osoba bywa w LinkedIn pod kilkoma adresami profilu (slug / ACoAA...) -- laczymy po nazwisku.
            t = _znajdz_po_nazwisku(c, nazwa, klucz, "", scisle=False)
        if not t:
            cur = c.execute("INSERT INTO teczki(klucz,nazwa,profil_url,naglowek,utworzono) VALUES(?,?,?,?,?)",
                            (klucz, nazwa or klucz, o.get("profile_url", ""), o.get("headline") or "", teraz()))
            tid, nowa = cur.lastrowid, True
        else:
            tid = t["id"]
            c.execute("UPDATE teczki SET naglowek=COALESCE(NULLIF(?,''),naglowek) WHERE id=?", (o.get("headline") or "", tid))

        def dodaj(kierunek, rodzaj, kiedy, tekst):
            h = _hash(tid, kierunek, kiedy, tekst)
            cur = c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts) "
                            "VALUES(?,?,?,?,?,?,?,?)", (tid, h, kierunek, rodzaj, kiedy, tekst.strip(), teraz(), parse_ts(kiedy)))
            return cur.rowcount

        for h in o.get("history") or []:
            if (h.get("text") or "").strip():
                dodaj("od_nas", {"letter": "list", "invite": "zaproszenie", "crm": "nasza odpowiedź"}.get(h.get("kind"), h.get("kind") or "wiadomość"),
                      h.get("ts") or "", h["text"])
        nowych = dodaj("od_leada", "odpowiedz", o.get("received") or o.get("reported_at") or "", o["text"])
        dodane += nowych
        if nowych or nowa:
            c.execute("UPDATE teczki SET do_oceny=1, przejrzana=0, ostatnia_wiadomosc=? WHERE id=?",
                      (o.get("received") or o.get("reported_at") or "", tid))
    return nowa, dodane


def nazwisko_imie(nazwa: str) -> str:
    baza = (nazwa or "").split(",")[0].replace(" -", "-")            # „Anna Kowalska, MBA” / „Szczęsna -Dymel”
    cz = [x for x in baza.split() if x.strip(".").lower() not in ("mba", "phd", "dr", "mgr", "inż")]
    return f"{cz[-1]} {' '.join(cz[:-1])}".strip() if len(cz) > 1 else (nazwa or "")


def teczki() -> list[dict]:
    """Wszystkie osoby wraz z decyzja; sortowanie wg nazwiska."""
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM wiadomosci w WHERE w.teczka_id=t.id AND w.ukryta=0 AND w.kierunek='od_leada') AS od_leada, "
            "(SELECT COUNT(*) FROM wiadomosci w WHERE w.teczka_id=t.id AND w.ukryta=0 AND w.kierunek='od_nas') AS od_nas, "
            "EXISTS(SELECT 1 FROM detektyw_zlecenia z WHERE z.teczka_id=t.id AND z.status='oczekuje') AS u_detektywa FROM teczki t")]
    for r in rows:
        r["nazwisko_imie"] = nazwisko_imie(r["nazwa"])
        r["ocena_ai"] = r["ocena"]
        if r.get("ocena_reczna") is not None:
            r["ocena"] = r["ocena_reczna"]                 # ocena ustawiona przez wlasciciela wygrywa z modelem
    return sorted(rows, key=lambda r: r["nazwisko_imie"].lower())


def teczka(tid: int) -> dict | None:
    with conn() as c:
        t = c.execute("SELECT * FROM teczki WHERE id=?", (tid,)).fetchone()
        if not t:
            return None
        w = [dict(r) for r in c.execute("SELECT * FROM wiadomosci WHERE teczka_id=? AND ukryta=0 ORDER BY id", (tid,))]
    # chronologicznie: od najstarszej; wiadomosci bez czytelnej daty na koncu (w kolejnosci wpisu)
    w.sort(key=lambda m: (m["ts"] == "", m["ts"], m["id"]))
    with conn() as c:
        udet = c.execute("SELECT 1 FROM detektyw_zlecenia WHERE teczka_id=? AND status='oczekuje'", (tid,)).fetchone() is not None
    d = {**dict(t), "wiadomosci": w, "ocena_ai": t["ocena"], "u_detektywa": udet}
    if d.get("ocena_reczna") is not None:
        d["ocena"] = d["ocena_reczna"]
    return d


def do_oceny(limit: int) -> list[dict]:
    with conn() as c:
        ids = [r["id"] for r in c.execute("SELECT id FROM teczki WHERE do_oceny=1 ORDER BY id LIMIT ?", (limit,))]
    return [teczka(i) for i in ids]


def zapisz_ocene(tid: int, r: dict, model: str):
    ocena = max(0, min(6, int(r.get("ocena") or 0)))
    if str(r.get("rodzaj") or "") in NIE_TECZKA:
        r = {**r, "zakladac": False}             # twarda zasada: odmowa / oferta pracy / rekrutacja / automat nigdy nie sa leadem
    with conn() as c:
        if str(r.get("rodzaj") or "") in NIE_TECZKA:
            # zdejmij z listy takze teczki „wymuszone” powiadomieniem LinkedIn (chyba ze wlasciciel dodal osobe recznie)
            c.execute("UPDATE teczki SET wymuszona=0, odrzucona_ai=1 WHERE id=? AND ocena_reczna IS NULL", (tid,))
        else:
            c.execute("UPDATE teczki SET odrzucona_ai=0 WHERE id=?", (tid,))
        for kol, klucz in (("miasto", "miasto"), ("telefon", "telefon"), ("email", "email"), ("www", "www"),
                           ("charakterystyka", "charakterystyka")):
            nowa = str(r.get(klucz) or "").strip()[:700]
            if kol in ("telefon", "email") and nowa and not _cudzy(nowa):
                nowa = ""                                   # to dane wlasciciela, nie osoby z teczki
            if kol == "charakterystyka" and c.execute("SELECT char_reczna FROM teczki WHERE id=?", (tid,)).fetchone()[0]:
                continue                                    # charakterystyka poprawiona recznie wygrywa z modelem
            if nowa and (kol == "charakterystyka" or not c.execute(f"SELECT {kol} FROM teczki WHERE id=?", (tid,)).fetchone()[0]):
                c.execute(f"UPDATE teczki SET {kol}=? WHERE id=?", (nowa, tid))      # reczne dane nie sa nadpisywane
        c.execute("UPDATE teczki SET do_oceny=0, pozytywna=?, rodzaj=?, termin=?, streszczenie=?, nastepny_krok=?, ocena=?, "
                  "model=?, ocenione=?, blad='' WHERE id=?",
                  (1 if r.get("zakladac") else 0, str(r.get("rodzaj") or "")[:60], str(r.get("termin_kontaktu") or "")[:120],
                   str(r.get("streszczenie") or "")[:800], str(r.get("nastepny_krok") or "")[:400], ocena, model, teraz(), tid))


def zapisz_blad(tid: int, blad: str):
    with conn() as c:
        c.execute("UPDATE teczki SET blad=? WHERE id=?", (blad[:400], tid))


def zakoncz_przebieg(zrodlo: str, **kw) -> dict:
    with conn() as c:
        c.execute("INSERT INTO przebiegi(czas,zrodlo,pobrano,nowych_teczek,nowych_wiadomosci,ocenionych,bledow,uwaga) VALUES(?,?,?,?,?,?,?,?)",
                  (teraz(), zrodlo, kw.get("pobrano", 0), kw.get("nowych_teczek", 0), kw.get("nowych_wiadomosci", 0),
                   kw.get("ocenionych", 0), kw.get("bledow", 0), kw.get("uwaga", "")))
    return {"czas": teraz(), "zrodlo": zrodlo, **kw}


def przebiegi(n: int = 1) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM przebiegi ORDER BY id DESC LIMIT ?", (n,))]


def liczniki() -> dict:
    with conn() as c:
        r = c.execute("SELECT COUNT(*) n, SUM((pozytywna=1 OR wymuszona=1) AND smietnik=0) p, SUM(do_oceny=1) d, "
            "SUM(NOT (pozytywna=1 OR wymuszona=1) OR smietnik=1) s FROM teczki").fetchone()
        w = c.execute("SELECT COUNT(*) n FROM wiadomosci WHERE kierunek='od_leada'").fetchone()
    return {"teczek": r["n"] or 0, "pozytywnych": r["p"] or 0, "do_oceny": r["d"] or 0, "smietnik_osoby": r["s"] or 0,
            "wiadomosci": w["n"] or 0}


# --------------------------------------------------------------- poczta -> projekty

def init_projekty():
    """Projekty poczty sa w bazie (mozna dopisywac nowe). Pierwszy raz: przenosimy dwa dawne (Plastema, PPIC) z ich promptami."""
    with conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS projekty (klucz TEXT PRIMARY KEY, nazwa TEXT NOT NULL, prompt TEXT NOT NULL DEFAULT '', "
                  "kolejnosc INTEGER NOT NULL DEFAULT 0)")
        try:
            c.execute("ALTER TABLE projekty ADD COLUMN rodzaj TEXT NOT NULL DEFAULT 'projekt'")      # projekt (czerwony) | inicjatywa (rozowy)
        except Exception:
            pass
        if not c.execute("SELECT 1 FROM projekty LIMIT 1").fetchone() and not ustawienie("projekty_przeniesione"):
            for i, (k, n) in enumerate((("plastema", "Plastema"), ("ppic", "redakcja PPIC"))):
                r = c.execute("SELECT v FROM ustawienia WHERE k=?", (f"prompt_{k}",)).fetchone()
                c.execute("INSERT INTO projekty(klucz,nazwa,prompt,kolejnosc) VALUES(?,?,?,?)", (k, n, r["v"] if r else "", i))
            c.execute("INSERT OR REPLACE INTO ustawienia(k,v) VALUES('projekty_przeniesione','1')")


def projekty() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM projekty ORDER BY kolejnosc, nazwa")]


KOLORY_RODZAJU = {"projekt": "czerwona", "inicjatywa": "rozowa"}


def dodaj_projekt(nazwa: str, rodzaj: str = "projekt") -> str | None:
    nazwa = re.sub(r"\s+", " ", nazwa or "").strip()[:80]
    if not nazwa:
        return None
    klucz = re.sub(r"[^a-z0-9]+", "-", nazwa.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))).strip("-") or "projekt"
    with conn() as c:
        baza, n = klucz, 2
        while c.execute("SELECT 1 FROM projekty WHERE klucz=?", (klucz,)).fetchone():
            klucz, n = f"{baza}-{n}", n + 1
        c.execute("INSERT INTO projekty(klucz,nazwa,rodzaj,kolejnosc) VALUES(?,?,?,(SELECT COALESCE(MAX(kolejnosc),0)+1 FROM projekty))",
                  (klucz, nazwa, rodzaj if rodzaj in KOLORY_RODZAJU else "projekt"))
    return klucz


def ustaw_wysoka(tid: int, wartosc: bool):
    """Fioletowa teczka: wysoka inicjatywa — osoba z szansa na pilny telefon."""
    with conn() as c:
        if wartosc and (c.execute("SELECT kolor FROM teczki WHERE id=?", (tid,)).fetchone() or {"kolor": ""})["kolor"] != "rozowa":
            return                                       # fioletowa tylko dla teczki z zalozona inicjatywa
        c.execute("UPDATE teczki SET wysoka=?, wysoka_auto=0 WHERE id=?", (1 if wartosc else 0, tid))


def _znacznik_telefonu(c, tid: int, dane: dict):
    """Detektyw szukal telefonu: gdy teczka nadal go nie ma, zapamietujemy „nie udalo sie ustalic”; znaleziony telefon zdejmuje znacznik."""
    tel = c.execute("SELECT telefon FROM teczki WHERE id=?", (tid,)).fetchone()["telefon"]
    c.execute("UPDATE teczki SET telefon_brak=? WHERE id=?", (0 if tel else 1, tid))


def ustaw_pilna(tid: int, wartosc: bool):
    """Lista pilnego obdzwonienia / kontaktu: niezalezna od koloru teczki; w kolumnie czas dodania (pusty = nie na liscie)."""
    with conn() as c:
        c.execute("UPDATE teczki SET pilna=?, pilna_auto=0 WHERE id=?", (teraz() if wartosc else "", tid))


def lista_pilna() -> list[dict]:
    """Teczki z listy pilnego kontaktu, od najdawniej dodanych."""
    zamknij_pilne_po_kontakcie()
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT id,nazwa,firma,stanowisko,telefon,email,pilna FROM teczki WHERE pilna<>'' AND smietnik=0 ORDER BY pilna, id")]


def ustaw_przejrzana(tid: int, wartosc: bool):
    with conn() as c:
        c.execute("UPDATE teczki SET przejrzana=? WHERE id=?", (1 if wartosc else 0, tid))


def przypisz_teczke(tid: int, klucz: str) -> bool:
    """Teczka nalezy do jednego projektu (czerwona) albo jednej inicjatywy (rozowa); pusty klucz = wypisanie."""
    with conn() as c:
        if not klucz:
            c.execute("UPDATE teczki SET projekt_klucz='', kolor='', wysoka=0 WHERE id=?", (tid,))
            return True
        p = c.execute("SELECT rodzaj FROM projekty WHERE klucz=?", (klucz,)).fetchone()
        if not p:
            return False
        c.execute("UPDATE teczki SET projekt_klucz=?, kolor=?, wysoka=CASE WHEN ?='rozowa' THEN wysoka ELSE 0 END WHERE id=?",
                  (klucz, KOLORY_RODZAJU[p["rodzaj"]], KOLORY_RODZAJU[p["rodzaj"]], tid))
    return True


def zapisz_prompty_projektow(prompty: dict[str, str]) -> bool:
    """Zwraca True, gdy cos sie zmienilo (wtedy poczte trzeba ocenic od nowa)."""
    zmiana = False
    with conn() as c:
        for k, v in prompty.items():
            r = c.execute("SELECT prompt FROM projekty WHERE klucz=?", (k,)).fetchone()
            if r and r["prompt"] != v.strip():
                c.execute("UPDATE projekty SET prompt=? WHERE klucz=?", (v.strip(), k))
                zmiana = True
    return zmiana


def usun_projekt(klucz: str):
    with conn() as c:
        c.execute("UPDATE teczki SET projekt_klucz='', kolor='' WHERE projekt_klucz=?", (klucz,))
        c.execute("DELETE FROM projekty WHERE klucz=?", (klucz,))
        c.execute("UPDATE poczta SET ocenione=0, projekt='' WHERE projekt=?", (klucz,))


def ostatnie_id_poczty() -> int:
    with conn() as c:
        return c.execute("SELECT COALESCE(MAX(id),0) m FROM poczta").fetchone()["m"]


def przyjmij_poczte(lista: list[dict]) -> int:
    n = 0
    with conn() as c:
        for m in lista:
            cur = c.execute("INSERT OR IGNORE INTO poczta(id,nadawca,temat,kiedy,tresc,zaimportowano) VALUES(?,?,?,?,?,?)",
                            (m["id"], m.get("sender") or "", m.get("subject") or "", m.get("received") or "",
                             m.get("body") or "", teraz()))
            n += cur.rowcount
    return n


def poczta_do_oceny(limit: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM poczta WHERE ocenione=0 ORDER BY id DESC LIMIT ?", (limit,))]


def zapisz_projekty(wyniki: dict[int, str]):
    with conn() as c:
        for i, proj in wyniki.items():
            c.execute("UPDATE poczta SET projekt=?, ocenione=1 WHERE id=?",
                      (proj if c.execute("SELECT 1 FROM projekty WHERE klucz=?", (proj,)).fetchone() else "", i))


def poczta_projektu(proj: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM poczta WHERE projekt=? ORDER BY kiedy DESC, id DESC", (proj,))]


def licznik_poczty() -> dict:
    with conn() as c:
        r = c.execute("SELECT SUM(ocenione=1 AND projekt='') sm, SUM(ocenione=0) d FROM poczta").fetchone()
        w = {x["projekt"]: x["n"] for x in c.execute("SELECT projekt, COUNT(*) n FROM poczta WHERE projekt<>'' GROUP BY projekt")}
    return {"projekty": w, "smietnik": r["sm"] or 0, "poczta_do_oceny": r["d"] or 0}


def przelicz_teczki():
    with conn() as c:
        c.execute("UPDATE teczki SET do_oceny=1, blad=''")


def przelicz_poczte():
    with conn() as c:
        c.execute("UPDATE poczta SET ocenione=0, projekt=''")


# --------------------------------------------------------------- ludzie, ktorzy napisali w LinkedIn (powiadomienia, wpis reczny)

_BEZ_DEDUP = ("powiadomienie", "informacja", "raport detektywa")


def _norm_tekst(t: str) -> str:
    return re.sub(r"[\W_]+", " ", (t or "").lower()).strip()


def _podobne(a: str, b: str, dzien_a: str = "", dzien_b: str = "") -> bool:
    """Ta sama wiadomosc, nawet gdy minimalnie sie rozni (spacje, interpunkcja, ucieta koncowka, dopisek). Krotkie teksty („ok”, „dziekuje”)
    sa duplikatem tylko tego samego dnia — ludzie piszą takie same krotkie wiadomosci w roznych dniach."""
    import difflib
    if not a or not b:
        return False
    if len(a) < 40 or len(b) < 40:
        if dzien_a and dzien_b and dzien_a != dzien_b:
            return False
        return a == b
    if a == b:
        return True
    k, d = (a, b) if len(a) <= len(b) else (b, a)
    if k in d and len(k) / len(d) >= 0.6:
        return True
    k, d = k[:3000], d[:3000]
    sm = difflib.SequenceMatcher(None, a[:3000], b[:3000], autojunk=False)
    return sm.real_quick_ratio() >= 0.85 and sm.quick_ratio() >= 0.85 and sm.ratio() >= 0.88


def _znajdz_podobna(c, tid: int, kierunek: str, tekst: str, kiedy: str):
    """Wiersz teczki z ta sama (prawie) wiadomoscia albo None."""
    if kierunek not in ("od_leada", "od_nas"):
        return None
    n = _norm_tekst(tekst)
    dz = (parse_ts(kiedy) or "")[:10]
    for r in c.execute("SELECT id, tekst, rodzaj, wlasna, ts FROM wiadomosci WHERE teczka_id=? AND kierunek=? AND ukryta=0", (tid, kierunek)):
        if (r["rodzaj"] or "") in _BEZ_DEDUP:
            continue
        if _podobne(n, _norm_tekst(r["tekst"]), dz, (r["ts"] or "")[:10]):
            return r
    return None


def przyjmij_osobe(o: dict, wymuszona: bool = True, jawnie: bool = False) -> tuple[bool, int]:
    """Zaklada teczke osobie, ktora napisala do nas w LinkedIn. Bez bramki AI: jesli napisala, ma teczke
    (wlasciciel moze ja wyrzucic do smietnika). Zwraca (nowa_teczka, nowych_wiadomosci)."""
    nazwa = (o.get("name") or "").strip()
    url = o.get("profile_url") or ""
    klucz = klucz_osoby(url, nazwa)
    if not klucz:
        return False, 0
    if not jawnie:                                # stare wpisy odpadaja; przy recznym zalozeniu wszystko zostaje
        o = {**o, "history": [h for h in o.get("history") or [] if not _stare(h.get("ts") or "")],
             "dates": [d for d in o.get("dates") or [] if not _stare(d)],
             "maile": [m for m in o.get("maile") or [] if not _stare(m.get("ts") or "")],
             "wydarzenia": [v for v in o.get("wydarzenia") or [] if not _stare(v.get("ts") or "")]}
    kont = o.get("contact") or {}
    firma = kont.get("company") or o.get("firma") or ""
    stan = kont.get("position") or o.get("stanowisko") or ""
    dodane = 0
    with conn() as c:
        if jawnie:
            c.execute("DELETE FROM skasowane WHERE klucz=? OR nazwa=?", (klucz, nazwa.lower()))
        elif _skasowana(c, klucz, nazwa):
            return False, 0
        tt = c.execute("SELECT id FROM teczki WHERE klucz=?", (klucz,)).fetchone() or _alias(c, klucz)
        if not tt and nazwa:
            tt = _znajdz_po_nazwisku(c, nazwa, klucz, url)        # dwie osoby o tym samym nazwisku, rozne PRAWDZIWE profile = dwie teczki
        if not tt and not jawnie and not (o.get("history") or o.get("dates") or o.get("maile") or o.get("wydarzenia") or o.get("wiadomosci")):
            return False, 0                       # nie zostalo nic od DATA_OD -- nie zakladamy pustej teczki
        if tt:
            tid, nowa = tt["id"], False
            c.execute("UPDATE teczki SET naglowek=COALESCE(NULLIF(?,''),naglowek), firma=COALESCE(NULLIF(?,''),firma), "
                      "stanowisko=COALESCE(NULLIF(?,''),stanowisko), watek_url=COALESCE(NULLIF(?,''),watek_url), "
                      "profil_url=COALESCE(NULLIF(profil_url,''),NULLIF(?,'')), wymuszona=CASE WHEN odrzucona_ai=1 AND ?=0 THEN wymuszona ELSE MAX(wymuszona,?) END WHERE id=?",
                      (o.get("headline") or "", firma, stan, o.get("thread_url") or "", url, int(jawnie), int(wymuszona), tid))
        else:
            cur = c.execute("INSERT INTO teczki(klucz,nazwa,profil_url,naglowek,firma,stanowisko,watek_url,wymuszona,utworzono,ocena_reczna) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?)", (klucz, nazwa or klucz, url, o.get("headline") or "", firma, stan,
                                                           o.get("thread_url") or "", int(wymuszona), teraz(),
                                                           4 if jawnie else None))     # wskazana przez wlasciciela = min. 4/6, do zmiany w teczce
            tid, nowa = cur.lastrowid, True

        def dodaj(kierunek, rodzaj, kiedy, tekst):
            podobna = _znajdz_podobna(c, tid, kierunek, tekst, kiedy)
            if podobna:                                   # juz jest — nie dublujemy; poprawiamy tylko wersje z importu na dluzsza/pelniejsza
                if not podobna["wlasna"] and len(tekst.strip()) > len(podobna["tekst"] or "") and rodzaj not in _BEZ_DEDUP:
                    c.execute("UPDATE wiadomosci SET tekst=? WHERE id=?", (tekst.strip(), podobna["id"]))
                return 0
            return c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts) VALUES(?,?,?,?,?,?,?,?)",
                             (tid, _hash(tid, kierunek, kiedy, tekst), kierunek, rodzaj, kiedy, tekst.strip(), teraz(), parse_ts(kiedy))).rowcount

        for h in o.get("history") or []:
            if (h.get("text") or "").strip():
                dodaj("od_nas", {"letter": "list", "invite": "zaproszenie", "crm": "nasza odpowiedź"}.get(h.get("kind"), "wiadomość"),
                      h.get("ts") or "", h["text"])
        for d in o.get("dates") or []:
            link = f" Otwórz wątek w LinkedIn: {o['thread_url']}" if o.get("thread_url") else ""
            dodane += dodaj("od_leada", "powiadomienie", d, "Napisał(a) do Ciebie w LinkedIn. Powiadomienie e-mail nie podaje treści "
                            "wiadomości." + link)
        for ml in o.get("maile") or []:               # prawdziwa korespondencja e-mail: wyslana i odebrana
            dodane += dodaj(ml.get("kierunek", "od_leada"), "e-mail", ml.get("ts") or "", ml.get("tekst") or ml.get("temat") or "")
            if ml.get("kierunek") == "od_nas" and nazwa:                       # adres odbiorcy = e-mail osoby
                nazw = nazwa.split()[-1].lower().replace("ł", "l")
                for adr in _RE_MAIL.findall(ml.get("do") or ""):
                    if nazw[:5] in adr.lower().replace("ł", "l") and _cudzy(adr):
                        c.execute("UPDATE teczki SET email=? WHERE id=? AND email=''", (adr, tid))
                        break
        for ev in o.get("wydarzenia") or []:          # kalendarz
            dodane += dodaj("zdarzenie", "spotkanie w kalendarzu", ev.get("ts") or "",
                            f"{ev.get('temat') or ''}" + (f" — {ev['miejsce']}" if ev.get("miejsce") else ""))
        for tekst in o.get("info") or []:             # co o osobie wie Kierownik (kontakt, aktywnosc, maile)
            dodane += dodaj("info", "informacja", teraz()[:10], tekst)
        for m in o.get("wiadomosci") or []:           # wpis reczny: wklejona tresc
            if (m.get("tekst") or "").strip():
                dodane += dodaj(m.get("kierunek", "od_leada"), m.get("rodzaj") or "wklejone", m.get("kiedy") or teraz()[:10], m["tekst"])
        if nowa or dodane:
            c.execute("UPDATE teczki SET do_oceny=1, smietnik=0, przejrzana=0 WHERE id=?", (tid,))
    return nowa, dodane


def dopisz_wiadomosc(tid: int, kierunek: str, tekst: str, kiedy: str = "", rodzaj: str = "wklejone"):
    """Reczny wpis do teczki. `kiedy` = czas ZDARZENIA (nie wpisu); bez niego bierzemy date z tekstu, a w ostatecznosci teraz."""
    if not tekst.strip():
        return
    kiedy = kiedy.strip() or data_z_tekstu(tekst) or teraz()[:16]
    if kierunek not in ("od_leada", "od_nas", "zdarzenie"):
        kierunek = "od_leada"
    if rodzaj == "wklejone" and _RE_TELEFON_TXT.search(tekst):
        rodzaj, kierunek = "rozmowa telefoniczna", ("zdarzenie" if kierunek != "od_leada" else kierunek)
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts,wlasna) VALUES(?,?,?,?,?,?,?,?,1)",
                  (tid, _hash(tid, kierunek, kiedy, tekst), kierunek, rodzaj, kiedy, tekst.strip(), teraz(), parse_ts(kiedy)))
        c.execute("UPDATE teczki SET do_oceny=1 WHERE id=?", (tid,))
    zamknij_pilne_po_kontakcie()


def edytuj_wiadomosc(mid: int, kierunek: str, rodzaj: str, data: str, godzina: str, tekst: str) -> int | None:
    """Poprawka WLASNEGO wpisu (dopisanego recznie). Zwraca id teczki albo None, gdy wpis nie istnieje / nie jest wlasny."""
    if not tekst.strip():
        return None
    if kierunek not in ("od_leada", "od_nas", "zdarzenie"):
        kierunek = "zdarzenie"
    kiedy = f"{data.strip()} {godzina.strip()}".strip() or teraz()[:16]
    with conn() as c:
        w = c.execute("SELECT teczka_id, wlasna, hash FROM wiadomosci WHERE id=?", (mid,)).fetchone()
        if not w:
            return None
        tid = w["teczka_id"]
        h = _hash(tid, kierunek, kiedy, tekst)
        if c.execute("SELECT 1 FROM wiadomosci WHERE hash=? AND id<>?", (h, mid)).fetchone():
            h = _hash(tid, kierunek, kiedy, tekst, mid)
        if not w["wlasna"]:
            h = w["hash"]                      # wpis z importu: hash zostaje, zeby kolejny import nie dodal oryginalu drugi raz
        c.execute("UPDATE wiadomosci SET kierunek=?, rodzaj=?, kiedy=?, ts=?, tekst=?, hash=? WHERE id=?",
                  (kierunek, rodzaj.strip() or "wklejone", kiedy, parse_ts(kiedy), tekst.strip(), h, mid))
        c.execute("UPDATE teczki SET do_oceny=1 WHERE id=?", (tid,))
    return tid


def usun_wiadomosc(mid: int) -> int | None:
    with conn() as c:
        w = c.execute("SELECT teczka_id, wlasna FROM wiadomosci WHERE id=?", (mid,)).fetchone()
        if not w:
            return None
        if w["wlasna"]:
            c.execute("DELETE FROM wiadomosci WHERE id=?", (mid,))
        else:
            c.execute("UPDATE wiadomosci SET ukryta=1 WHERE id=?", (mid,))      # import nie przywroci wpisu (ten sam hash)
        c.execute("UPDATE teczki SET do_oceny=1 WHERE id=?", (w["teczka_id"],))
    return w["teczka_id"]


def smietnik(tid: int, wartosc: int):
    with conn() as c:
        c.execute("UPDATE teczki SET smietnik=? WHERE id=?", (wartosc, tid))


def kasuj(tid: int):
    """Kasuje teczke razem z cala zawartoscia i zapamietuje ja, zeby automaty jej nie zalozyly od nowa."""
    with conn() as c:
        tt = c.execute("SELECT klucz, nazwa FROM teczki WHERE id=?", (tid,)).fetchone()
        if not tt:
            return
        c.execute("INSERT OR REPLACE INTO skasowane(klucz,nazwa,kiedy) VALUES(?,?,?)", (tt["klucz"], tt["nazwa"].lower(), teraz()))
        c.execute("DELETE FROM wiadomosci WHERE teczka_id=?", (tid,))
        c.execute("DELETE FROM teczki WHERE id=?", (tid,))


def ustaw_ocene(tid: int, ocena: int | None):
    with conn() as c:
        c.execute("UPDATE teczki SET ocena_reczna=? WHERE id=?", (None if ocena is None else max(0, min(6, ocena)), tid))


def istnieje(profil_url: str, nazwa: str) -> bool:
    klucz = klucz_osoby(profil_url, nazwa)
    with conn() as c:
        return bool(c.execute("SELECT 1 FROM teczki WHERE klucz=?", (klucz,)).fetchone() or _alias(c, klucz) or (nazwa and _znajdz_po_nazwisku(c, nazwa, klucz, "", scisle=False)))


def bez_rozmowy() -> list[dict]:
    """Teczki na liscie, w ktorych nie ma jeszcze zadnej tresci rozmowy (tylko powiadomienia / informacje)."""
    with conn() as c:
        rows = c.execute(
            "SELECT t.id, t.nazwa, t.profil_url, t.watek_url FROM teczki t WHERE (t.pozytywna=1 OR t.wymuszona=1) AND t.smietnik=0 AND t.kolor<>'zielona' "
            "AND NOT EXISTS (SELECT 1 FROM wiadomosci w WHERE w.teczka_id=t.id AND (w.kierunek='rozmowa' OR w.rodzaj IN ('wklejone','odpowiedz')))")
        return [dict(r) for r in rows]


_RE_TEL = re.compile(r"(?<![\d])(?:\+?48[\s-]?)?(?:\d{3}[\s-]?\d{3}[\s-]?\d{3}|\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2})(?![\d])")
_RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


WLASCICIEL = [x.strip().lower() for x in os.getenv("OWNER_KONTAKT", "695450085,wtm695450085,sigmaquality,moszczynski,audyt-aiact").split(",") if x.strip()]


def _cudzy(wartosc: str) -> bool:
    """Telefon / e-mail wlasciciela (podpis w jego wlasnych wiadomosciach) nie moze trafic do teczki cudzej osoby."""
    cyfry = re.sub(r"\D", "", wartosc or "")
    w = (wartosc or "").lower()
    return not any(x in w or (x.isdigit() and x in cyfry) for x in WLASCICIEL)


def wyciagnij_kontakty(wiadomosci: list[dict]) -> dict:
    """Telefon i e-mail wprost z tresci wiadomosci OD OSOBY (nie z naszych ofert)."""
    tekst = "\n".join(m["tekst"] for m in wiadomosci if m["kierunek"] in ("od_leada", "rozmowa", "wklejone"))
    tekst_bez_maili = _RE_MAIL.sub(" ", tekst)                       # cyfry w adresie e-mail to nie telefon
    tel = next((x.group(0).strip() for x in _RE_TEL.finditer(tekst_bez_maili) if _cudzy(x.group(0))), "")
    mail = next((x.group(0) for x in _RE_MAIL.finditer(tekst) if _cudzy(x.group(0))), "")
    return {"telefon": tel, "email": mail}


def zapisz_dane(tid: int, miasto: str, telefon: str, email: str, www: str, firma: str, stanowisko: str,
                nazwa: str | None = None, profil_url: str | None = None, watek_url: str | None = None, charakterystyka: str | None = None):
    """Reczna edycja wszystkich pol teczki. Puste pole = kasujemy wartosc. Zmiana adresu profilu przestawia tez klucz teczki
    (chyba ze ma go juz inna teczka)."""
    with conn() as c:
        c.execute("UPDATE teczki SET miasto=?, telefon=?, email=?, www=?, firma=?, stanowisko=?, telefon_brak=CASE WHEN ?<>'' THEN 0 ELSE telefon_brak END WHERE id=?",
                  (miasto.strip(), telefon.strip(), email.strip(), www.strip(), firma.strip(), stanowisko.strip(), telefon.strip(), tid))
        if nazwa is not None and nazwa.strip():
            c.execute("UPDATE teczki SET nazwa=? WHERE id=?", (re.sub(r"\s+", " ", nazwa.strip()), tid))
        if watek_url is not None:
            c.execute("UPDATE teczki SET watek_url=? WHERE id=?", (watek_url.strip(), tid))
        if charakterystyka is not None:
            c.execute("UPDATE teczki SET charakterystyka=?, char_reczna=1 WHERE id=?", (charakterystyka.strip(), tid))
        if profil_url is not None:
            t = c.execute("SELECT nazwa, profil_url, klucz FROM teczki WHERE id=?", (tid,)).fetchone()
            if profil_url.strip() != (t["profil_url"] or ""):
                c.execute("UPDATE teczki SET profil_url=? WHERE id=?", (profil_url.strip(), tid))
                nowy = klucz_osoby(profil_url, t["nazwa"])
                if nowy and nowy != t["klucz"] and not c.execute("SELECT 1 FROM teczki WHERE klucz=? AND id<>?", (nowy, tid)).fetchone():
                    c.execute("UPDATE teczki SET klucz=? WHERE id=?", (nowy, tid))


def przyjmij_lead_wywiadu(l: dict) -> tuple[bool, bool]:
    """Lead od Wywiadowcy = ZIELONA teczka: osoba mowi wazne rzeczy, ale nie wiemy, jak sie z nia skontaktowac.
    Zwraca (nowa_teczka, nowe_zlecenie_detektywa). Bez bramki AI i bez szukania rozmow -- nie ma jeszcze zadnej."""
    nazwa = re.sub(r"\s+", " ", str(l.get("name") or "").strip())
    url = str(l.get("linkedin_url") or "").strip()
    klucz = klucz_osoby(url, nazwa)
    if not klucz or len(nazwa.split()) < 2:
        return False, False
    try:
        zaang = max(1, min(6, int(l.get("engagement") or 1)))
    except (TypeError, ValueError):
        zaang = 1
    sektor = l.get("sector") if l.get("sector") in ("produkcyjny", "uslugowy") else ""
    vip = 1 if l.get("vip") else 0
    with conn() as c:
        if _skasowana(c, klucz, nazwa):
            return False, False
        t = c.execute("SELECT id FROM teczki WHERE klucz=?", (klucz,)).fetchone() or _alias(c, klucz) or _znajdz_po_nazwisku(c, nazwa, klucz, "", scisle=False)
        nowa = t is None
        if nowa:
            tid = c.execute(
                "INSERT INTO teczki(klucz,nazwa,profil_url,firma,stanowisko,miasto,wymuszona,do_oceny,utworzono,wywiad_zaang,kolor,sektor,vip) "
                "VALUES(?,?,?,?,?,?,1,0,?,?,'zielona',?,?)",
                (klucz, nazwa, url, l.get("company") or "", l.get("position") or "", l.get("city") or "", teraz(), zaang,
                 sektor, vip)).lastrowid
            tekst = "Wywiadowca: " + (l.get("why") or "osoba publicznie mówi o AI w firmie") + "."
            if l.get("quote"):
                tekst += f" Cytat: „{str(l['quote']).strip('„”\"“ ')}”."
            if l.get("source_url"):
                tekst += f" Źródło: {l.get('source_name') or ''} {l['source_url']}" + (f" ({l['said_on']})" if l.get("said_on") else "")
            c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts) VALUES(?,?,?,?,?,?,?,?)",
                      (tid, _hash(tid, "wywiadowca", tekst), "info", "informacja", teraz()[:10], tekst, teraz(), teraz()[:16]))
        else:
            tid = t["id"]
            c.execute("UPDATE teczki SET sektor=COALESCE(NULLIF(?,''),sektor), vip=MAX(vip,?) WHERE id=?", (sektor, vip, tid))
    nowe_zlecenie = False       # Detektyw sam pobiera liste z Wywiadowcy; Analityk tylko zaklada zielona teczke
    return nowa, nowe_zlecenie


def wynik_detektywa_osoby(d: dict) -> bool:
    """Wynik Detektywa dla osoby z listy Wywiadowcy: znajdujemy teczke po nazwisku (albo zakladamy zielona) i uzupelniamy."""
    nazwa = re.sub(r"\s+", " ", str(d.get("nazwa") or "").strip())
    if len(nazwa.split()) < 2:
        return False
    with conn() as c:
        li0 = str(d.get("linkedin_url") or "").strip()
        t = _znajdz_po_nazwisku(c, nazwa, klucz_osoby(li0, ""), li0)
    if not t:
        przyjmij_lead_wywiadu({"name": nazwa, "company": d.get("firma"), "position": d.get("stanowisko"), "city": d.get("miasto"),
                               "engagement": d.get("zaangazowanie") or 3, "sector": d.get("sektor"), "vip": d.get("vip")})
        with conn() as c:
            t = _znajdz_po_nazwisku(c, nazwa, "", "", scisle=False)
        if not t:
            return False
    tid, wynik = t["id"], str(d.get("wynik") or "").strip()
    with conn() as c:
        li = str(d.get("linkedin_url") or "").strip()
        if li.startswith("http"):
            c.execute("UPDATE teczki SET profil_url=? WHERE id=? AND profil_url=''", (li, tid))
        for kol in ("telefon", "email", "miasto", "www"):
            v = str(d.get(kol) or "").strip()
            if v and (kol not in ("telefon", "email") or _cudzy(v)):
                c.execute(f"UPDATE teczki SET {kol}=? WHERE id=? AND {kol}=''", (v, tid))
        if wynik:
            c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts) VALUES(?,?,?,?,?,?,?,?)",
                      (tid, _hash(tid, "detektyw", wynik), "zdarzenie", "raport detektywa", teraz()[:16], wynik, teraz(), teraz()[:16]))
        _znacznik_telefonu(c, tid, d)
        if any(str(d.get(k) or "").strip() for k in ("linkedin_url", "telefon", "email", "www")):
            # Detektyw cos znalazl: kontakt jest, wiec zielona (szukamy kontaktu) znika -- teczka robi sie biala i znow „nieprzejrzana”
            c.execute("UPDATE teczki SET kolor=CASE WHEN kolor='zielona' THEN '' ELSE kolor END, przejrzana=0 WHERE id=?", (tid,))
    return True


# --------------------------------------------------------------- detektyw (aplikacja detektywa jeszcze nie istnieje: zlecenia czekaja w kolejce)

def dodaj_zlecenie(tid: int, prompt: str, tryb: str = "pelny") -> int:
    """tryb: pelny (kontakt, LinkedIn, miejsca) albo telefon (detektyw szuka WYLACZNIE numeru telefonu)."""
    with conn() as c:
        try:
            c.execute("ALTER TABLE detektyw_zlecenia ADD COLUMN tryb TEXT NOT NULL DEFAULT 'pelny'")
        except Exception:
            pass
        return c.execute("INSERT INTO detektyw_zlecenia(teczka_id,prompt,utworzono,tryb) VALUES(?,?,?,?)",
                         (tid, prompt.strip(), teraz(), "telefon" if tryb == "telefon" else "pelny")).lastrowid


def zlecenia_teczki(tid: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM detektyw_zlecenia WHERE teczka_id=? ORDER BY id DESC", (tid,))]


def zlecenia_otwarte() -> list[dict]:
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT z.id, z.teczka_id, z.prompt, z.tryb, z.utworzono, t.nazwa, t.stanowisko, t.firma, t.miasto, t.profil_url, t.telefon, t.email, t.www "
            "FROM detektyw_zlecenia z JOIN teczki t ON t.id=z.teczka_id WHERE z.status='oczekuje' ORDER BY z.id")]
    return rows


def zapisz_wynik_detektywa(zid: int, wynik: str, dane: dict) -> bool:
    """Detektyw odsyla znaleziony kontakt: wynik trafia do teczki jako zdarzenie, a puste pola kontaktowe sie uzupelniaja."""
    with conn() as c:
        z = c.execute("SELECT teczka_id FROM detektyw_zlecenia WHERE id=?", (zid,)).fetchone()
        if not z:
            return False
        tid = z["teczka_id"]
        c.execute("UPDATE detektyw_zlecenia SET status='wykonane', wynik=?, zakonczono=? WHERE id=?", (wynik.strip(), teraz(), zid))
        li = str(dane.get("linkedin_url") or "").strip()
        if li.startswith("http"):
            c.execute("UPDATE teczki SET profil_url=? WHERE id=? AND profil_url=''", (li, tid))
        for kol in ("telefon", "email", "miasto", "www"):
            v = str(dane.get(kol) or "").strip()
            if v and (kol not in ("telefon", "email") or _cudzy(v)):
                c.execute(f"UPDATE teczki SET {kol}=? WHERE id=? AND {kol}=''", (v, tid))
        c.execute("INSERT OR IGNORE INTO wiadomosci(teczka_id,hash,kierunek,rodzaj,kiedy,tekst,zaimportowano,ts) VALUES(?,?,?,?,?,?,?,?)",
                  (tid, _hash(tid, "detektyw", zid, wynik), "zdarzenie", "raport detektywa", teraz()[:16], wynik.strip(), teraz(), teraz()[:16]))
        _znacznik_telefonu(c, tid, dane)
    return True


def teczka_osoby(url: str, nazwa: str):
    """Istniejaca teczka tej osoby (po adresie profilu; po nazwisku tylko gdy nie ma homonimu z innym adresem) albo None."""
    klucz = klucz_osoby(url, nazwa)
    with conn() as c:
        t = c.execute("SELECT id FROM teczki WHERE klucz=?", (klucz,)).fetchone() or _alias(c, klucz)
        if not t and nazwa:
            t = _znajdz_po_nazwisku(c, nazwa, klucz, url)
        return t["id"] if t else None


def przyjmij_dialog(d: dict) -> tuple[bool, int]:
    """Dialog z LinkedIn od agenta (obie strony, z datami) -> wlasciwa teczka. Teczke zakladamy, gdy osoba cos napisala (albo juz ja mamy);
    dialog, w ktorym pisalismy tylko my i nie ma teczki, pomijamy."""
    wiad = []
    for m in d.get("wiadomosci") or []:
        t = (m.get("tekst") or "").strip()
        if t:
            kierunek = "od_leada" if m.get("kierunek") == "od_leada" else "od_nas"
            wiad.append({"kierunek": kierunek, "rodzaj": "wiadomość LinkedIn", "kiedy": (m.get("ts") or "").strip() or teraz()[:16], "tekst": t})
    if not wiad:
        return False, 0
    url = (d.get("profile_url") or "").strip()
    if teczka_osoby(url, (d.get("name") or "").strip()) is None and not any(m["kierunek"] == "od_leada" for m in wiad):
        return False, 0
    return przyjmij_osobe({"name": d.get("name"), "profile_url": url, "headline": d.get("headline"), "wiadomosci": wiad}, wymuszona=True, jawnie=False)


# --------------------------------------------------------------- duplikaty teczek, lista pilna po kontakcie

def norma_nazwy(n: str) -> str:
    """Nazwisko do porownan: same litery, male, bez emoji/flag/ozdobnikow („Michal Jucha 🇵🇱” = „Michal Jucha”)."""
    return " ".join("".join(ch if ch.isalpha() else " " for ch in (n or "").lower()).split())


def _profil_nieczytelny(klucz: str, url: str = "") -> bool:
    """Wewnetrzny identyfikator LinkedIn (ACoAA...), profil z emoji albo brak profilu — nie da sie go wiarygodnie porownac z adresem-slugiem."""
    k = (klucz or "").lower()
    return "/in/acoaa" in k or "/" not in k or not (url or klucz) or any(ord(ch) > 0x2000 for ch in k)


def _alias(c, klucz: str):
    return c.execute("SELECT teczka_id AS id FROM aliasy a WHERE klucz=? AND EXISTS(SELECT 1 FROM teczki t WHERE t.id=a.teczka_id)", (klucz,)).fetchone()


def _znajdz_po_nazwisku(c, nazwa: str, klucz: str, url: str, scisle: bool = True):
    """Teczka tej samej osoby pod innym adresem profilu. scisle: dwa rozne prawdziwe slugi = dwie osoby."""
    n = norma_nazwy(nazwa)
    for cand in c.execute("SELECT id, nazwa, klucz, profil_url FROM teczki ORDER BY id"):
        if norma_nazwy(cand["nazwa"]) != n:
            continue
        if (not scisle or not url or not cand["profil_url"] or cand["klucz"] == klucz
                or _profil_nieczytelny(klucz, url) or _profil_nieczytelny(cand["klucz"], cand["profil_url"])):
            return cand
    return None


def scal_teczki(zrodlo: int, cel: int) -> bool:
    """Wlewa teczke `zrodlo` do `cel`: wiadomosci (bez dubli), dane, kolory, zlecenia; stary adres profilu zostaje aliasem."""
    if zrodlo == cel:
        return False
    with conn() as c:
        z, t = (c.execute("SELECT * FROM teczki WHERE id=?", (i,)).fetchone() for i in (zrodlo, cel))
        if not z or not t:
            return False
        for m in c.execute("SELECT * FROM wiadomosci WHERE teczka_id=? ORDER BY id", (zrodlo,)).fetchall():
            dubel = _znajdz_podobna(c, cel, m["kierunek"], m["tekst"], m["kiedy"]) if not m["ukryta"] else None
            c.execute("UPDATE wiadomosci SET teczka_id=?, ukryta=? WHERE id=?", (cel, 1 if (dubel or m["ukryta"]) else 0, m["id"]))
        for kol in ("miasto", "telefon", "email", "www", "firma", "stanowisko", "watek_url", "profil_url", "charakterystyka", "sektor", "kolor", "projekt_klucz"):
            if not t[kol] and z[kol]:
                c.execute(f"UPDATE teczki SET {kol}=? WHERE id=?", (z[kol], cel))
        c.execute("UPDATE teczki SET ocena_reczna=COALESCE(ocena_reczna,?), vip=MAX(vip,?), wysoka=MAX(wysoka,?), "
                  "wysoka_auto=CASE WHEN wysoka=0 THEN ? ELSE wysoka_auto END, pilna=CASE WHEN pilna='' THEN ? ELSE pilna END, "
                  "pilna_auto=CASE WHEN pilna='' THEN ? ELSE pilna_auto END, wymuszona=MAX(wymuszona,?), pozytywna=MAX(pozytywna,?), do_oceny=1 WHERE id=?",
                  (z["ocena_reczna"], z["vip"], z["wysoka"], z["wysoka_auto"], z["pilna"], z["pilna_auto"], z["wymuszona"], z["pozytywna"], cel))
        c.execute("UPDATE detektyw_zlecenia SET teczka_id=? WHERE teczka_id=?", (cel, zrodlo))
        c.execute("UPDATE zalecenia SET teczka_id=? WHERE teczka_id=?", (cel, zrodlo))
        c.execute("UPDATE aliasy SET teczka_id=? WHERE teczka_id=?", (cel, zrodlo))
        c.execute("INSERT OR REPLACE INTO aliasy(klucz,teczka_id) VALUES(?,?)", (z["klucz"], cel))
        c.execute("DELETE FROM teczki WHERE id=?", (zrodlo,))
        mapa = json.loads((c.execute("SELECT v FROM ustawienia WHERE k='scalone_id'").fetchone() or {"v": "{}"})["v"] or "{}")
        mapa = {k: (cel if v == zrodlo else v) for k, v in mapa.items()}
        mapa[str(zrodlo)] = cel                    # stare odprawy wskazuja skasowane id — render mapuje je na teczke docelowa
        c.execute("INSERT OR REPLACE INTO ustawienia(k,v) VALUES('scalone_id',?)", (json.dumps(mapa),))
    return True


def scalone_id() -> dict[int, int]:
    try:
        return {int(k): int(v) for k, v in json.loads(ustawienie("scalone_id", "{}") or "{}").items()}
    except ValueError:
        return {}


def scal_duplikaty(jawne: list[tuple[int, int]] | None = None) -> list[str]:
    """Scala teczki tej samej osoby (to samo nazwisko; adres-slug vs ACoAA/emoji). `jawne` = pary (zrodlo, cel) wskazane recznie."""
    zrobione = [f"{zr}→{ce}" for zr, ce in jawne or [] if scal_teczki(zr, ce)]
    with conn() as c:
        wiersze = [dict(r) for r in c.execute("SELECT t.id, t.nazwa, t.klucz, t.profil_url, (SELECT COUNT(*) FROM wiadomosci w WHERE w.teczka_id=t.id) AS m FROM teczki t")]
    grupy: dict[str, list[dict]] = {}
    for r in wiersze:
        grupy.setdefault(norma_nazwy(r["nazwa"]), []).append(r)
    for n, g in grupy.items():
        if not n or len(g) < 2:
            continue
        g.sort(key=lambda r: (-r["m"], r["id"]))               # cel = najbogatsza teczka
        cel = g[0]
        for r in g[1:]:
            if _profil_nieczytelny(r["klucz"], r["profil_url"]) or _profil_nieczytelny(cel["klucz"], cel["profil_url"]):
                if scal_teczki(r["id"], cel["id"]):
                    zrobione.append(f'{r["nazwa"]}: {r["id"]}→{cel["id"]}')
    return zrobione


def zamknij_pilne_po_kontakcie() -> int:
    """Wlasciciel dopisal w teczce rozmowe/spotkanie/notatke po dodaniu na liste pilnych = sprawa zalatwiona: zdejmij z listy (i zalecenie telefonu)."""
    n = 0
    with conn() as c:
        for t in c.execute("SELECT id, pilna FROM teczki WHERE pilna<>''").fetchall():
            kontakt = c.execute(
                "SELECT 1 FROM wiadomosci WHERE teczka_id=? AND ukryta=0 AND ((wlasna=1 AND kierunek<>'od_leada') OR rodzaj IN ('rozmowa telefoniczna','spotkanie','notatka')) "
                "AND (ts>? OR (ts LIKE '% 00:00' AND substr(ts,1,10)>=substr(?,1,10)))", (t["id"], t["pilna"][:16], t["pilna"])).fetchone()
            if kontakt:
                c.execute("UPDATE teczki SET pilna='', pilna_auto=0, wysoka=CASE WHEN wysoka_auto=1 THEN 0 ELSE wysoka END, wysoka_auto=0 WHERE id=?", (t["id"],))
                c.execute("UPDATE zalecenia SET status='wykonane', zamknieto=? WHERE teczka_id=? AND status='otwarte'", (teraz(), t["id"]))
                n += 1
    return n
