"""Odprawa strategiczna Analityka: przechodzi przez wszystkie aktywne teczki i mowi, co jest pilne, a co perspektywiczne.

Dwa etapy (145 teczek nie miesci sie sensownie w jednym zapytaniu):
1. paczki po kilkanascie teczek -> krotki raport o kazdej osobie (stan rozmowy, kto ma ruch, pilnosc, perspektywa, powiazania),
2. jedno zapytanie na raportach wszystkich osob -> plan: najwazniejsze na jutro, w tygodniu, perspektywiczne, powiazania, do odpuszczenia.
"""
import json
import logging
import re
import threading
from datetime import datetime, timedelta

import ai
import store

log = logging.getLogger("strateg")
_zamek = threading.Lock()
PACZKA = 12
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
MODEL_DOMYSLNY = "gpt-5.5"                 # silnik API
MODEL_SDK_DOMYSLNY = "gpt-6-sol"            # silnik SDK (abonament; 6.1-sol nie działa na koncie ChatGPT): odprawa na mocniejszym modelu niz ocena teczek (Luna)

KONTEKST_DOMYSLNY = (
    "Właściciel (Wojciech) sprzedaje wdrożenia AI firmom, głównie produkcyjnym i z parkiem maszynowym. Kontakty pochodzą z LinkedIn "
    "(listy i zaproszenia), z maili, rozmów telefonicznych i spotkań. Liczy się przychód w najbliższych tygodniach, ale też "
    "relacje, które dojrzewają dłużej. Jest jedną osobą: ma czas na kilka konkretnych kontaktów dziennie, nie na 145.")

INSTRUKCJA_PACZKI = (
    "Jesteś analitykiem sprzedaży B2B i doradcą strategicznym właściciela. Dostajesz paczkę teczek osób (tablica JSON). "
    "Dla KAŻDEJ teczki z paczki oceń sytuację tak, jak zrobiłby to doświadczony handlowiec, który czyta całą korespondencję: "
    "kto ostatni się odezwał, czy czeka się na nas, czy my na nich, czy padł termin, czy była rozmowa lub spotkanie, "
    "czy ostatnia wiadomość wymaga reakcji, czy telefon ma sens teraz, czy lepiej poczekać (np. wysłaliśmy maila wczoraj), "
    "czy osoba się wycofuje. Wpisy 'rozmowa telefoniczna', 'spotkanie', 'notatka' i 'wklejone' to ustalenia właściciela — "
    "mają pierwszeństwo. Dni od ostatniego kontaktu i kto pisał ostatni są policzone w danych — nie przeliczaj ich. "
    "Pole czeka_na_nas_dni (liczba) oznacza, że OSTATNIĄ wiadomość napisał klient i nie odpowiedzieliśmy — to czerwona flaga; "
    "czytaj tę wiadomość uważnie i wyciągnij z niej konkret: prośba o telefon (i czy mamy numer), propozycja terminu, przekazanie kontaktu do INNEJ osoby "
    "(imię, nazwisko, e-mail — wpisz je w 'dlaczego', to jest sprawa do załatwienia: napisać do tej osoby), pytanie, zgoda na rozmowę. "
    "Pole zalegly_telefon_od_dni (liczba) oznacza, że wcześniej zalecono telefon, a w teczce nie ma wpisu, że się odbył — to zaległość, "
    "pilność 9-10. Zwróć uwagę na ludzi z tej samej firmy, branży, miasta lub wspominających się nawzajem (pole 'powiazania'). "
    "NIE ZMYŚLAJ: opieraj się wyłącznie na danych teczki. Jeśli korespondencji jest mało, napisz to i obniż pewność.\n"
    "Odpowiedz WYŁĄCZNIE obiektem JSON: {\"osoby\":[{\"id\":0,\"stan\":\"1 zdanie: gdzie jest rozmowa\","
    "\"kto_ma_ruch\":\"my|klient|nikt\",\"pilnosc\":0,\"perspektywa\":0,\"akcja\":\"zadzwonić|napisać|spotkanie|czekać|odpuścić\","
    "\"kiedy\":\"np. jutro rano / do piątku / po 20.10 / bez terminu\",\"ocena\":0,\"dlaczego\":\"1-2 zdania, konkret z korespondencji\","
    "\"powiazania\":\"inne osoby/firmy z paczki lub z treści, albo pusty\",\"pewnosc\":\"wysoka|srednia|niska\"}]}. "
    "ocena 0-6 = Twoja ocena zaangażowania i szansy tej osoby po przeczytaniu CAŁEJ korespondencji i wpisów właściciela (nadpisuje wcześniejszą "
    "ocenę ciepłości, która bywa zaniżona): 0-1 brak sygnału lub wycofanie, 2 chłodno, 3 jednorazowa uprzejma odpowiedź bez ruchu, "
    "4 klient sam pisze merytorycznie, dopytuje lub odpowiada na kolejne wiadomości, 5 podał termin, poprosił o szczegóły albo odbyła się rozmowa, "
    "6 umówione/odbyte spotkanie, klient czeka na naszą ofertę lub konkretny ruch, prosi o kontakt. Ocenę dawaj niezależnie od tego, kto ma ruch. "
    "pilnosc 0-10 = jak bardzo trzeba zareagować w najbliższych dniach (10 = każda godzina zwłoki kosztuje). "
    "Pilnosc >= 8 ustaw, gdy klient napisał świeżo (czeka_na_nas_dni <= 3) i NIE jest to odmowa, albo gdy po spotkaniu/rozmowie trzeba wykonać uzgodniony ruch, "
    "albo klient sam podał termin, który wypada teraz; klient aktywnie zaangażowany, który czeka na odpowiedź, to nigdy nie jest pilnosc poniżej 7. "
    "Jeśli osoba ma wpis właściciela o rozmowie/spotkaniu NOWSZY niż ostatnia wiadomość klienta i nie ustalono pilnego kolejnego kroku, pilnosc <= 3. "
    "perspektywa 0-10 = jak duży potencjał ma ta relacja w horyzoncie miesięcy, niezależnie od pilności. "
    "Dokładnie po jednym wpisie dla każdego id z paczki. Jeśli osoba ma mozliwy_duplikat_teczki_id, zaznacz to w polu 'powiazania'.")

INSTRUKCJA_PLANU = (
    "Jesteś szefem sprzedaży i doradcą strategicznym właściciela. Dostajesz raporty o wszystkich aktywnych teczkach (po jednym na "
    "osobę, z ocenami pilności i perspektywy) oraz dzisiejszą datę. Ułóż odprawę: co właściciel ma zrobić w najbliższy dzień roboczy "
    "i w tym tygodniu, kto jest perspektywiczny, jakie są powiązania między klientami i czego nie ruszać. "
    "Myśl strategicznie: porównuj osoby między sobą (kogo najpierw, jeśli jest czas na 5 kontaktów), szukaj powiązań (ta sama firma, "
    "polecenia, ta sama branża — jedna rozmowa może otworzyć kilka drzwi), uwzględniaj kolejność i timing (nie dzwoń dzień po mailu; "
    "dzwoń tam, gdzie klient sam podał termin lub czeka na ofertę), a przy kontaktach bez szansy powiedz wprost, że warto odpuścić. "
    "Do każdej pozycji dodaj 'jak_zaczac': konkretne pierwsze zdanie rozmowy lub maila. NIE ZMYŚLAJ faktów spoza raportów; "
    "używaj tylko id z raportów. Dostajesz też blok 'teraz' z kalendarzy i poczty (spotkania i rozmowy na dziś i jutro, pilne sprawy, "
    "propozycje i oferty) — uwzględnij go w nagłówku i planie. Osoby z zalegly_telefon_od_dni MUSZĄ być w na_jutro z akcją zadzwonić. "
    "Osoby z czeka_na_nas_dni <= 2 to świeże odpowiedzi klientów: domyślnie trafiają do na_jutro (chyba że odpowiedź jest odmową). "
    "Jeśli klient przekazał kontakt do innej osoby, 'jak_zaczac' ma być wiadomością do TEJ osoby. "
    "NIGDY nie podawaj numerów id w tekstach dla człowieka (naglowek, dlaczego, opis, uwagi) — pisz imię i nazwisko (ewentualnie firmę); id służy tylko w polach \"id\"/\"ids\". Jeśli osoba ma mozliwy_duplikat_teczki_id, to ta sama osoba występuje w kilku teczkach — traktuj ją jako JEDNĄ osobę, nie wymieniaj jej dwa razy, w polu id wybierz teczkę z bogatszą korespondencją, a w \"dlaczego\" zaznacz, że teczki warto scalić.\n"
    "Odpowiedz WYŁĄCZNIE obiektem JSON: {\"naglowek\":\"2-3 zdania: jaki jest obraz sytuacji i główna rada na jutro\","
    "\"na_jutro\":[{\"id\":0,\"priorytet\":1,\"akcja\":\"zadzwonić|napisać|spotkanie\",\"kiedy\":\"np. jutro 9:00-10:00\","
    "\"dlaczego\":\"\",\"jak_zaczac\":\"\",\"ryzyko\":\"co się stanie, jeśli tego nie zrobię\"}],"
    "\"w_tym_tygodniu\":[{\"id\":0,\"akcja\":\"\",\"kiedy\":\"\",\"dlaczego\":\"\",\"jak_zaczac\":\"\"}],"
    "\"perspektywiczne\":[{\"id\":0,\"dlaczego\":\"\",\"kiedy_wrocic\":\"\",\"co_podtrzymac\":\"\"}],"
    "\"powiazania\":[{\"ids\":[0],\"opis\":\"\",\"jak_wykorzystac\":\"\"}],"
    "\"odpuscic\":[{\"id\":0,\"powod\":\"\"}],\"uwagi_strategiczne\":\"3-6 zdań: wzorce, luki, co zmienić w sposobie pracy\"}. "
    "na_jutro: najwyżej 7 pozycji, w kolejności priorytetu 1,2,3... w_tygodniu: najwyżej 12. perspektywiczne: najwyżej 15. "
    "odpuscic: tylko osoby, które wyraźnie nie mają sensu (ze wskazaniem powodu).")


# --------------------------------------------------------------- dane

def _dzis() -> datetime:
    return datetime.now(store.TZ)


def _aktywne() -> list[dict]:
    return [t for t in store.teczki() if (t["pozytywna"] or t["wymuszona"]) and not t["smietnik"]]


def _wpis(m: dict) -> dict:
    return {"kierunek": m["kierunek"], "rodzaj": m["rodzaj"], "kiedy": m["ts"] or m["kiedy"], "tekst": m["tekst"][:500]}


def _duplikaty(lista: list[dict]) -> dict[int, list[int]]:
    """Ta sama osoba w kilku teczkach (inny adres profilu): id -> id pozostalych."""
    grupy: dict[str, list[int]] = {}
    for t in lista:
        grupy.setdefault(store.norma_nazwy(t["nazwa"]), []).append(t["id"])
    return {i: [x for x in ids if x != i] for ids in grupy.values() if len(ids) > 1 for i in ids}


def _rodzenstwo(wszystkie: list[dict]) -> dict[int, list[int]]:
    """id -> id innych teczek tej samej osoby, takze nieaktywnych (odpowiedz bywa w drugiej teczce, np. 'Tomasz Aniol')."""
    grupy: dict[str, list[int]] = {}
    for t in wszystkie:
        grupy.setdefault(store.norma_nazwy(t["nazwa"]), []).append(t["id"])
    return {i: [x for x in ids if x != i] for ids in grupy.values() if len(ids) > 1 for i in ids}


def _wpis_wlasciciela(m: dict) -> bool:
    """Rozmowa, spotkanie, notatka albo wpis wlasciciela. Wklejona wiadomosc KLIENTA (kierunek od_leada) to nie wpis wlasciciela."""
    return m["rodzaj"] in ("spotkanie", "rozmowa telefoniczna", "notatka") or (bool(m.get("wlasna")) and m["kierunek"] != "od_leada")


def _karta(t: dict, dzis: datetime, rodzenstwo: list[int] | None = None, zalegly: int | None = None) -> dict:
    """Skrot teczki: dane + ostatnie wiadomosci + wszystkie wpisy wlasne wlasciciela (rozmowy, spotkania, notatki)."""
    pelna = store.teczka(t["id"])
    w = list(pelna["wiadomosci"])
    for r in rodzenstwo or []:                          # wiadomosci z drugiej teczki tej samej osoby
        inna = store.teczka(r)
        if inna:
            w += [m for m in inna["wiadomosci"] if m["rodzaj"] != "informacja" and not any(x["hash"] == m["hash"] for x in w)]
    w.sort(key=lambda m: (m["ts"] == "", m["ts"], m["id"]))
    datowane = [m for m in w if m["ts"]]
    ostatnia = max(datowane, key=lambda m: m["ts"]) if datowane else None
    dni = None
    if ostatnia:
        try:
            dni = (dzis.date() - datetime.strptime(ostatnia["ts"][:10], "%Y-%m-%d").date()).days
        except ValueError:
            pass
    wlasne = [m for m in w if _wpis_wlasciciela(m)]
    reszta = [m for m in w if m not in wlasne][-5:]
    wybrane = sorted(wlasne[-6:] + reszta, key=lambda m: (m["ts"] == "", m["ts"], m["id"]))
    czeka = None
    if (ostatnia and ostatnia["kierunek"] == "od_leada" and dni is not None and not _wpis_wlasciciela(ostatnia)
            and ostatnia["rodzaj"] not in ("spotkanie", "rozmowa telefoniczna", "notatka", "wklejone")
            and t["rodzaj"] not in ("odmowa", "oferta_pracy", "automat")):       # wpis wlasciciela albo odmowa to nie „czekamy na odpowiedz”
        czeka = dni
    # tresc do pokazania: ostatnia prawdziwa wiadomosc klienta (powiadomienie LinkedIn bez tresci tylko gdy nic innego nie ma)
    prawdziwe = [m for m in w if m["kierunek"] == "od_leada" and m["rodzaj"] != "powiadomienie" and m["ts"]]
    pokaz = max(prawdziwe, key=lambda m: m["ts"]) if prawdziwe and ostatnia and prawdziwe[-1]["ts"][:10] >= ostatnia["ts"][:10] else ostatnia
    watek = pelna.get("watek_url") or next((x.group(0) for m in reversed(w) for x in [re.search(r"https://www\.linkedin\.com/\S+", m["tekst"])] if x), "")
    tekst_pokaz = ("Napisał(a) w LinkedIn — powiadomienie nie pokazuje treści, otwórz wątek." if pokaz and pokaz["rodzaj"] == "powiadomienie"
                   else (pokaz["tekst"][:350] if pokaz else ""))
    return {"id": t["id"], "osoba": t["nazwa"], "stanowisko": t["stanowisko"], "firma": t["firma"], "miasto": t["miasto"],
            "czeka_na_nas_dni": czeka, "zalegly_telefon_od_dni": zalegly, "_ostatnia": tekst_pokaz, "_watek": watek.rstrip(").,"),
            "_ostatnia_ts": (pokaz["ts"] if pokaz else ""),
            "ma_telefon": bool(t["telefon"]), "ocena_cieplosci_0_6": int(t["ocena"]), "rodzaj_odpowiedzi": t["rodzaj"],
            "termin_zapowiedziany_przez_klienta": t["termin"], "streszczenie": t["streszczenie"], "charakterystyka": t["charakterystyka"],
            "wlasciciel_oznaczyl_pilne": bool(t["pilna"]), "wlasciciel_oznaczyl_wysoka_inicjatywa": bool(t["wysoka"]),
            "dni_od_ostatniego_kontaktu": dni, "ostatni_pisal": (ostatnia["kierunek"] if ostatnia else "nieznany"),
            "liczba_wiadomosci": len(w), "mozliwy_duplikat_teczki_id": [], "korespondencja": [_wpis(m) for m in wybrane]}


def _naglowek_dnia(dzis: datetime) -> str:
    nast = dzis + timedelta(days=1)
    while nast.weekday() >= 5:
        nast += timedelta(days=1)
    return (f"Dzisiaj jest {DNI[dzis.weekday()]} {dzis:%Y-%m-%d}. Najbliższy dzień roboczy to {DNI[nast.weekday()]} {nast:%Y-%m-%d}. "
            "Daty w korespondencji porównuj z dzisiejszą (terminy typu „koniec października” mogą już minąć lub być tuż-tuż).")


def nowe_od_klientow(karty: list[dict]) -> list[dict]:
    """Swieze odpowiedzi klientow (ostatnia wiadomosc od klienta, <= 4 dni), jedna pozycja na osobe."""
    widziani, nowe = set(), []
    for k in sorted((k for k in karty if k["czeka_na_nas_dni"] is not None and k["czeka_na_nas_dni"] <= 4), key=lambda k: k["_ostatnia_ts"], reverse=True):
        nazwa = store.norma_nazwy(k["osoba"])
        if nazwa not in widziani:                          # ta sama osoba w dwoch teczkach = jeden wpis
            widziani.add(nazwa)
            nowe.append({"id": k["id"], "dni": k["czeka_na_nas_dni"], "kiedy": k["_ostatnia_ts"], "tekst": k["_ostatnia"], "url": k["_watek"]})
    return nowe


def teraz_z_kierownika() -> dict | None:
    """Spotkania/rozmowy na dziś i jutro, pilne i propozycje z kalendarzy i poczty (Kierownik)."""
    import os
    import requests
    token = os.getenv("KIEROWNIK_EXECUTOR_TOKEN", "")
    if not token:
        return None
    try:
        r = requests.get(os.getenv("KIEROWNIK_URL", "http://kierownik:8000").rstrip("/") + "/api/executor/now",
                         headers={"X-Executor-Token": token}, timeout=30)
        r.raise_for_status()
        dane = r.json()
        dane.pop("pending_category", None)            # licznik techniczny Kierownika, model brał go za „82 sprawy”
        return dane
    except Exception as e:
        log.warning("teraz z Kierownika: %s", e)
        return None


def zalegle_telefony(dzis: datetime) -> dict[int, dict]:
    """Zalecone wczesniej telefony, po ktorych w teczce nie ma wpisu wlasciciela (rozmowa, spotkanie, notatka, wklejone) — ataki do skutku.
    Zdjecie z listy pilnej klawiszem ✕ NIE zamyka zalecenia: liczy sie tylko wpis w teczce."""
    wynik = {}
    with store.conn() as c:
        otwarte = [dict(r) for r in c.execute("SELECT * FROM zalecenia WHERE status='otwarte' AND akcja='zadzwonić' ORDER BY id")]
        for z in otwarte:
            t = c.execute("SELECT smietnik FROM teczki WHERE id=?", (z["teczka_id"],)).fetchone()
            zrobione = c.execute("SELECT 1 FROM wiadomosci WHERE teczka_id=? AND ukryta=0 AND substr(ts,1,10)>=? AND "
                                 "((wlasna=1 AND kierunek<>'od_leada') OR rodzaj IN ('rozmowa telefoniczna','spotkanie','notatka'))", (z["teczka_id"], z["utworzono"][:10])).fetchone()
            if not t or t["smietnik"] or zrobione:
                c.execute("UPDATE zalecenia SET status='wykonane', zamknieto=? WHERE id=?", (store.teraz(), z["id"]))
                continue
            dni = (dzis.date() - datetime.strptime(z["utworzono"][:10], "%Y-%m-%d").date()).days
            if dni >= 1 and z["teczka_id"] not in wynik:
                wynik[z["teczka_id"]] = {"id": z["teczka_id"], "dni": dni, "od": z["utworzono"][:10]}
    return wynik


def _zastosuj_plan(plan: dict, zalegle: dict[int, dict]) -> None:
    """Telefony z planu na liste pilnego kontaktu; zalegle zawsze wracaja na gore na_jutro; zapis zalecen do pilnowania."""
    na_jutro = plan.get("na_jutro") or []
    ids = {int(p["id"]) for p in na_jutro if str(p.get("id", "")).lstrip("-").isdigit()}
    for z in sorted(zalegle.values(), key=lambda x: -x["dni"]):
        if z["id"] not in ids:
            na_jutro.insert(0, {"id": z["id"], "akcja": "zadzwonić", "kiedy": "jutro rano — zaległe",
                                "dlaczego": f"Zaległy telefon: zalecony {z['od']} ({z['dni']} dni temu), a w teczce nie ma wpisu, że rozmowa się odbyła.",
                                "jak_zaczac": "", "ryzyko": "Im dłużej zwlekasz, tym mniejsza szansa na rozmowę."})
    for n, p in enumerate(na_jutro, 1):
        p["priorytet"] = n
        if int(p.get("id", 0)) in zalegle:
            p["zalegle_dni"] = zalegle[int(p["id"])]["dni"]
    plan["na_jutro"] = na_jutro
    plan["_zalegle"] = list(zalegle.values())
    with store.conn() as c:
        for lista in ("na_jutro", "w_tym_tygodniu"):
            for p in plan.get(lista) or []:
                try:
                    tid = int(p["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                akcja = str(p.get("akcja") or "").lower()
                if lista == "na_jutro" and akcja in ("zadzwonić", "spotkanie"):
                    for sid in _siostry(tid) or [tid]:
                        c.execute("UPDATE teczki SET pilna=?, pilna_auto=1 WHERE id=? AND pilna=''", (store.teraz(), sid))      # lista pilnego kontaktu
                if akcja == "zadzwonić" and not c.execute("SELECT 1 FROM zalecenia WHERE teczka_id=? AND status='otwarte' AND akcja='zadzwonić'", (tid,)).fetchone():
                    c.execute("INSERT INTO zalecenia(teczka_id,akcja,kiedy,utworzono) VALUES(?,?,?,?)", (tid, "zadzwonić", str(p.get("kiedy") or ""), store.teraz()))


def _siostry(tid: int) -> list[int]:
    """Teczka + wszystkie teczki tej samej osoby (to samo nazwisko), takze nieaktywne."""
    with store.conn() as c:
        n = c.execute("SELECT nazwa FROM teczki WHERE id=?", (tid,)).fetchone()
        if not n:
            return []
        norm = store.norma_nazwy(n["nazwa"])
        return [r["id"] for r in c.execute("SELECT id, nazwa FROM teczki").fetchall() if store.norma_nazwy(r["nazwa"]) == norm]


def zastosuj_raporty(raporty: dict[int, dict]) -> dict:
    """Analityk strategiczny ma wplyw na teczki: ocena 0-6 (gdy wlasciciel nie ustawil recznej), fiolet (alarm) i lista pilnych.
    Flagi ustawione przez automat (…_auto) automat tez zdejmuje; ustawione recznie przez wlasciciela zostaja."""
    zmiany = {"ocena": 0, "alarm": 0, "pilne": 0, "zdjete": 0}
    grupy: dict[tuple, list[dict]] = {}
    for tid, r in raporty.items():
        ids = tuple(sorted(_siostry(tid) or [tid]))
        grupy.setdefault(ids, []).append({**r, "id": tid})
    with store.conn() as c:
        for ids, rs in grupy.items():
            r = max(rs, key=lambda x: (int(x.get("pilnosc") or 0), int(x.get("ocena") or 0)))     # najmocniejszy raport z siostrzanych teczek
            pil = int(r.get("pilnosc") or 0)
            akcja = str(r.get("akcja") or "").lower()
            ruch = str(r.get("kto_ma_ruch") or "").lower()
            ocena = max((int(x.get("ocena") or 0) for x in rs), default=0) if any(str(x.get("ocena", "")).strip() != "" for x in rs) else None
            for tid in ids:
                if ocena is not None:
                    pewnosc = str(r.get("pewnosc") or "").lower()
                    biez = c.execute("SELECT ocena FROM teczki WHERE id=? AND ocena_reczna IS NULL", (tid,)).fetchone()
                    if biez and (pewnosc != "niska" or ocena > biez["ocena"]) and ocena != biez["ocena"]:
                        c.execute("UPDATE teczki SET ocena=? WHERE id=?", (max(0, min(6, ocena)), tid))
                        zmiany["ocena"] += 1
                if pil >= 8 and akcja not in ("odpuścić",) and ruch != "klient":
                    if c.execute("UPDATE teczki SET wysoka=1, wysoka_auto=CASE WHEN wysoka=1 AND wysoka_auto=0 THEN 0 ELSE 1 END WHERE id=? AND wysoka=0", (tid,)).rowcount:
                        zmiany["alarm"] += 1
                    if c.execute("UPDATE teczki SET pilna=?, pilna_auto=1 WHERE id=? AND pilna=''", (store.teraz(), tid)).rowcount:
                        zmiany["pilne"] += 1
                elif pil <= 3 or akcja in ("czekać", "odpuścić"):
                    zd = c.execute("UPDATE teczki SET pilna='', pilna_auto=0 WHERE id=? AND pilna<>'' AND pilna_auto=1", (tid,)).rowcount
                    zd += c.execute("UPDATE teczki SET wysoka=0, wysoka_auto=0 WHERE id=? AND wysoka=1 AND wysoka_auto=1", (tid,)).rowcount
                    zmiany["zdjete"] += zd
    return zmiany


def ustawienia() -> dict:
    modele = ai.modele()
    domyslny = MODEL_DOMYSLNY if MODEL_DOMYSLNY in modele else store.ustawienie("model", ai.MODEL_DOMYSLNY)
    return {"model": store.ustawienie("model_strateg", "") or domyslny,
            "model_sdk": store.ustawienie("model_sdk_odprawa", "") or MODEL_SDK_DOMYSLNY,
            "kontekst": store.ustawienie("kontekst_strateg", "") or KONTEKST_DOMYSLNY}


# --------------------------------------------------------------- przebieg

def _postep(oid: int, tekst: str):
    with store.conn() as c:
        c.execute("UPDATE odprawy SET postep=? WHERE id=?", (tekst, oid))


def _wykonaj(oid: int):
    ust = ustawienia()
    dzis = _dzis()
    dzien = _naglowek_dnia(dzis)
    store.ustaw("szybki_ts", store.teraz())          # od tej chwili „nowe” dla szybkiego przegladu w ciagu dnia
    try:
        aktywne = _aktywne()
        dup = _duplikaty(aktywne)
        rodz = _rodzenstwo(store.teczki())
        zalegle = zalegle_telefony(dzis)
        teraz = teraz_z_kierownika()
        karty = [_karta(t, dzis, rodz.get(t["id"]), zalegle.get(t["id"], {}).get("dni")) for t in aktywne]
        for k in karty:
            k["mozliwy_duplikat_teczki_id"] = dup.get(k["id"], [])
        nowe = nowe_od_klientow(karty)
        for k in karty:
            k.pop("_ostatnia", None), k.pop("_ostatnia_ts", None), k.pop("_watek", None)
        raporty: dict[int, dict] = {}
        for i in range(0, len(karty), PACZKA):
            grupa = karty[i:i + PACZKA]
            _postep(oid, f"Czytam teczki {i + 1}-{i + len(grupa)} z {len(karty)}")
            r = ai.wyluskaj_json(ai.zapytaj(
                ust["model"], INSTRUKCJA_PACZKI + "\n\nKONTEKST WŁAŚCICIELA:\n" + ust["kontekst"] + "\n\n" + dzien,
                json.dumps(grupa, ensure_ascii=False), False, rozumowanie="medium", model_sdk_zadania=ust["model_sdk"], timeout=600))
            for o in r.get("osoby") or []:
                if str(o.get("id", "")).isdigit():
                    raporty[int(o["id"])] = o
        brak = [k["id"] for k in karty if k["id"] not in raporty]
        _postep(oid, f"Układam plan ({len(raporty)} z {len(karty)} teczek ocenionych)")
        wejscie = [{**{"id": k["id"], "osoba": k["osoba"], "firma": k["firma"], "stanowisko": k["stanowisko"], "miasto": k["miasto"],
                       "dni_od_ostatniego_kontaktu": k["dni_od_ostatniego_kontaktu"], "ostatni_pisal": k["ostatni_pisal"],
                       "ma_telefon": k["ma_telefon"], "cieplosc_0_6": k["ocena_cieplosci_0_6"],
                       "termin_klienta": k["termin_zapowiedziany_przez_klienta"], "czeka_na_nas_dni": k["czeka_na_nas_dni"],
                       "zalegly_telefon_od_dni": k["zalegly_telefon_od_dni"]}, **{x: v for x, v in raporty[k["id"]].items() if x != "id"}}
                   for k in karty if k["id"] in raporty]
        wejscie.sort(key=lambda x: -(int(x.get("pilnosc") or 0) * 2 + int(x.get("perspektywa") or 0)))
        plan = ai.wyluskaj_json(ai.zapytaj(
            ust["model"], INSTRUKCJA_PLANU + "\n\nKONTEKST WŁAŚCICIELA:\n" + ust["kontekst"] + "\n\n" + dzien,
            json.dumps({"teraz": teraz, "teczki": wejscie}, ensure_ascii=False), False, rozumowanie="high", model_sdk_zadania=ust["model_sdk"], timeout=1500))
        plan["_dzien"] = dzien
        plan["_teraz"] = teraz
        plan["_nowe_od_klientow"] = nowe
        plan["_zmiany_teczek"] = zastosuj_raporty(raporty)
        _zastosuj_plan(plan, zalegle)
        plan["_teczek"] = len(karty)
        plan["_bez_raportu"] = brak
        with store.conn() as c:
            c.execute("UPDATE odprawy SET status='gotowa', wynik=?, raporty=?, postep='', zakonczono=? WHERE id=?",
                      (json.dumps(plan, ensure_ascii=False), json.dumps(list(raporty.values()), ensure_ascii=False), store.teraz(), oid))
    except Exception as e:
        log.exception("odprawa")
        with store.conn() as c:
            c.execute("UPDATE odprawy SET status='blad', blad=?, postep='', zakonczono=? WHERE id=?",
                      ("Brak środków na koncie OpenAI (insufficient_quota) — doładuj konto na platform.openai.com/settings/organization/billing."
                       if "insufficient_quota" in str(e) else f"{type(e).__name__}: {e}"[:600], store.teraz(), oid))
    finally:
        _zamek.release()


def uruchom(zrodlo: str = "ręcznie") -> dict:
    """Start w tle. Naraz chodzi jedna odprawa."""
    if not ai.wlaczone():
        return {"ok": False, "uwaga": "Brak OPENAI_API_KEY"}
    if not _zamek.acquire(blocking=False):
        return {"ok": False, "uwaga": "Odprawa już trwa"}
    ust = ustawienia()
    with store.conn() as c:
        oid = c.execute("INSERT INTO odprawy(czas,zrodlo,model,status) VALUES(?,?,?, 'trwa')", (store.teraz(), zrodlo, ust["model_sdk"] if ai.silnik() == "sdk" else ust["model"])).lastrowid
    threading.Thread(target=_wykonaj, args=(oid,), daemon=True).start()
    return {"ok": True, "id": oid}


def ostatnia() -> dict | None:
    with store.conn() as c:
        r = c.execute("SELECT * FROM odprawy ORDER BY id DESC LIMIT 1").fetchone()
        gotowa = c.execute("SELECT * FROM odprawy WHERE status='gotowa' ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return None
    d = dict(r)
    g = dict(gotowa) if gotowa else None
    d["plan"] = json.loads(g["wynik"]) if g else None
    d["plan_czas"] = g["czas"] if g else ""
    d["plan_model"] = g["model"] if g else ""
    return d


# --------------------------------------------------------------- szybki przeglad w ciagu dnia

def szybki_przeglad() -> dict:
    """Nocna odprawa nie zna wiadomosci z dnia. Co tick: teczki z NOWA wiadomoscia klienta albo wpisem wlasciciela od ostatniego przegladu
    dostaja ten sam raport co w odprawie (ocena, pilnosc, akcja) i te same skutki: ocena, fiolet, lista pilnych, wpis w „napisali do Ciebie”."""
    if not ai.wlaczone() or not _zamek.acquire(blocking=False):
        return {"ok": False}
    try:
        od = store.ustawienie("szybki_ts", "")
        if not od:
            o = ostatnia()
            od = (o or {}).get("plan_czas") or store.teraz()
        teraz_ts = store.teraz()
        with store.conn() as c:
            ids = {r["teczka_id"] for r in c.execute(
                "SELECT DISTINCT teczka_id FROM wiadomosci WHERE zaimportowano>? AND ukryta=0 AND rodzaj NOT IN ('informacja','raport detektywa') "
                "AND (kierunek='od_leada' OR wlasna=1)", (od,))}
        store.zamknij_pilne_po_kontakcie()
        dzis = _dzis()
        aktywne = {t["id"]: t for t in _aktywne()}
        dotkniete = {i for tid in ids for i in _siostry(tid)} & set(aktywne)
        if not dotkniete:
            store.ustaw("szybki_ts", teraz_ts)
            return {"ok": True, "teczek": 0}
        ust = ustawienia()
        dzien = _naglowek_dnia(dzis)
        rodz = _rodzenstwo(store.teczki())
        zalegle = zalegle_telefony(dzis)
        dup = _duplikaty(list(aktywne.values()))
        karty = [_karta(aktywne[i], dzis, rodz.get(i), zalegle.get(i, {}).get("dni")) for i in sorted(dotkniete)]
        for k in karty:
            k["mozliwy_duplikat_teczki_id"] = dup.get(k["id"], [])
        czyste = [{x: v for x, v in k.items() if not x.startswith("_")} for k in karty]
        raporty: dict[int, dict] = {}
        for i in range(0, len(czyste), PACZKA):
            r = ai.wyluskaj_json(ai.zapytaj(
                ust["model"], INSTRUKCJA_PACZKI + "\n\nKONTEKST WŁAŚCICIELA:\n" + ust["kontekst"] + "\n\n" + dzien,
                json.dumps(czyste[i:i + PACZKA], ensure_ascii=False), False, rozumowanie="medium", model_sdk_zadania=ust["model_sdk"], timeout=600))
            for o in r.get("osoby") or []:
                if str(o.get("id", "")).isdigit():
                    raporty[int(o["id"])] = o
        zmiany = zastosuj_raporty(raporty)
        _dopisz_do_planu(karty, raporty)
        store.ustaw("szybki_ts", teraz_ts)
        log.info("szybki przeglad: %s teczek, %s", len(karty), zmiany)
        return {"ok": True, "teczek": len(karty), **zmiany}
    except Exception as e:
        log.warning("szybki przeglad: %s", e)
        return {"ok": False, "blad": f"{type(e).__name__}: {e}"[:300]}
    finally:
        _zamek.release()


def _dopisz_do_planu(karty: list[dict], raporty: dict[int, dict]) -> None:
    """Ostatnia gotowa odprawa: odswiez „napisali do Ciebie” i dopisz pilne osoby (pilnosc >= 8), ktorych w planie nie ma."""
    with store.conn() as c:
        g = c.execute("SELECT id, wynik FROM odprawy WHERE status='gotowa' ORDER BY id DESC LIMIT 1").fetchone()
        if not g:
            return
        plan = json.loads(g["wynik"])
        aktualne = {n["id"]: n for n in plan.get("_nowe_od_klientow") or []}
        for n in nowe_od_klientow(karty):
            for i in _siostry(n["id"]):
                aktualne.pop(i, None)
            aktualne[n["id"]] = n
        plan["_nowe_od_klientow"] = sorted(aktualne.values(), key=lambda n: n["kiedy"], reverse=True)
        w_planie = {i for l in ("na_jutro", "w_tym_tygodniu") for p in plan.get(l) or [] for i in _siostry(int(p["id"]))
                    if str(p.get("id", "")).isdigit()}
        dopisane = plan.setdefault("_dopisane_w_dzien", [])
        for tid, r in raporty.items():
            if int(r.get("pilnosc") or 0) >= 8 and tid not in w_planie and str(r.get("akcja") or "").lower() != "odpuścić":
                dopisane[:] = [d for d in dopisane if d["id"] != tid]
                dopisane.append({"id": tid, "akcja": r.get("akcja") or "napisać", "kiedy": r.get("kiedy") or "dziś",
                                 "dlaczego": r.get("dlaczego") or r.get("stan") or "", "stan": r.get("stan") or "", "czas": store.teraz()[:16]})
        c.execute("UPDATE odprawy SET wynik=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), g["id"]))
