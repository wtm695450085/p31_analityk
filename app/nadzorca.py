"""Agent Analityka.

1. Zaklada teczki: kazda osoba, ktora odpisala na wiadomosc z LinkedIn, ma teczke ze wszystkim, co od niej przyszlo
   (oraz tym, co do niej wyslalismy).
2. Ocenia teczki modelem: czy odpowiedz jest POZYTYWNA (odezwie sie, podal termin, zapamieta kontakt, zainteresowanie).

Dane wpadaja dwiema drogami: Kierownik wysyla je przyciskiem (POST /api/kierownik/odpowiedzi), a Agent (n8n) co 30 minut
sam je pobiera z Kierownika (GET /api/executor/replies). Duplikaty odsiewa hash wiadomosci.
"""
import csv
import io
import json
import logging
import re
import os
import threading

import requests

import ai
import store

log = logging.getLogger("hermes")
_zamek = threading.Lock()
KIEROWNIK = os.getenv("KIEROWNIK_URL", "http://kierownik:8000").rstrip("/")
TOKEN_KIER = os.getenv("KIEROWNIK_EXECUTOR_TOKEN", "")

PROMPT_DOMYSLNY = (
    "Zakładamy teczki tylko w dwóch przypadkach:\n"
    "Przypadek pierwszy: zakładamy teczkę dla osób, które po otrzymaniu naszej wiadomości marketingowej (listu) "
    "wygenerowanego przez naszego agenta GPT, piszą coś, co nie jest odmową.\n"
    "Przypadek drugi: zakładamy teczkę dla osób, które piszą, że chcą AI.\n"
    "Uwaga: nie zakładamy teczek nikomu więcej, zwłaszcza tym, którzy chcą mnie zatrudnić jako pracownika "
    "lub współpracownika B2B.")

PROMPT_DETEKTYWA = (
    "Ta osoba wyraziła chęć współpracy, ale nie podała żadnego namiaru. Znajdź kontakt do niej: adres e-mail, telefon, adres firmy "
    "oraz miejsca, gdzie można ją spotkać (biuro, zakład, wydarzenia branżowe, targi, konferencje, w których uczestniczy).\n"
    "Osoba: {nazwisko}. Stanowisko: {stanowisko}. Firma: {firma}. Miasto: {miasto}. LinkedIn: {linkedin}.\n"
    "Korzystaj wyłącznie z publicznie dostępnych źródeł (strona firmy, rejestry KRS/CEIDG, profil LinkedIn, publikacje, strony wydarzeń). "
    "Zwróć: e-mail, telefon, adres, gdzie ją spotkać, ŹRÓDŁO każdej informacji i pewność (pewne / prawdopodobne).")

PROMPT_TELEFONU = (
    "Znajdź tylko numer telefonu tej osoby. Najważniejszy jest telefon komórkowy; telefon stacjonarny jest mniej ważny "
    "(podaj go, gdy komórkowego nie ma, albo dodatkowo). Tylko to, nic więcej — nie szukaj o niej niczego innego.\n"
    "Osoba: {nazwisko}. Stanowisko: {stanowisko}. Firma: {firma}. Miasto: {miasto}. LinkedIn: {linkedin}.")

# Pusty prompt projektu = nic nie trafia do projektu (wlasciciel opisuje, od kogo przychodzi poczta tego projektu).
PODPOWIEDZ_PROJEKTU = "Opisz, jakie osoby (imię i nazwisko), adresy e-mail lub domena firmowa należą do tego projektu."

INSTRUKCJA = (
    "NAJWAŻNIEJSZA ZASADA, nadrzędna nad wszystkim innym: oferty pracy NIE są leadami. Jeśli osoba proponuje nam pracę, "
    "rolę, stanowisko, rekrutację, kontrakt B2B jako wykonawcy, współpracę w roli pracownika/specjalisty, wysyła ofertę z portalu "
    "pracy albo pyta „czy jest Pan zainteresowany stanowiskiem” — to zakladac=false i rodzaj=\"oferta_pracy\", nawet jeśli "
    "wiadomość „nie jest odmową” i brzmi uprzejmie. Dotyczy to też rekruterów i firm szukających pracowników. "
    "Dotyczy to także osób, które OFERUJĄ SIEBIE jako pracownika/kandydata („jestem otwarty na nowe możliwości zawodowe”, "
    "przedstawia swój profil i doświadczenie, szuka pracy) — to też rodzaj=\"oferta_pracy\", zakladac=false. "
    "ODMOWA to nie lead: każda wiadomość typu „dziękuję, ale nie zajmujemy się tym / nie jesteśmy zainteresowani / nie potrzebujemy” "
    "to rodzaj=\"odmowa\" i zakladac=false — bez wyjątków, nawet jeśli jest uprzejma i podpisana. "
    "Uwrażliwienie na oferty pracy i odmowy jest priorytetem właściciela.\n"
    "Jesteś analitykiem sprzedaży B2B. Dostajesz teczkę kandydata: chronologiczną korespondencję z LinkedIn "
    "(od_nas = to, co wysłaliśmy; od_leada = to, co napisała osoba). O tym, czy zakładamy teczkę, decydują WYŁĄCZNIE "
    "kryteria właściciela podane poniżej — trzymaj się ich dosłownie.\n"
    "Ciepłość 0-6 (jak bardzo osoba jest zainteresowana współpracą): 0 = brak sygnału, 3 = „zapamiętam kontakt”, "
    "4 = „odezwę się” / zainteresowanie, 5 = termin lub prośba o szczegóły, 6 = chce rozmowy. "
    "Jeśli jedyną wiadomością od osoby jest powiadomienie bez treści (rodzaj \"powiadomienie\"), to osoba i tak do nas napisała — "
    "daj ocenę 3 i w następnym kroku wpisz: otworzyć wątek w LinkedIn i przeczytać.\n"
    "DANE KONTAKTOWE I CHARAKTERYSTYKA: wyciągnij z korespondencji (i, jeśli masz wyszukiwanie, z oficjalnej strony firmy lub profilu) "
    "miasto, telefon, e-mail i stronę www firmy. NIE ZMYŚLAJ — nieznane zostaw puste. Telefon i e-mail tylko takie, które naprawdę "
    "widziałeś. Pole charakterystyka to DOKŁADNIE 3 zdania: kim jest (rola, firma, branża, wielkość) / co i jak mówił o AI, problemach "
    "lub współpracy / dlaczego to lead i co robimy dalej.\n"
    "Odpowiedz WYŁĄCZNIE obiektem JSON: {\"zakladac\":true,\"powod\":\"który przypadek z kryteriów albo dlaczego nie\","
    "\"rodzaj\":\"odezwie_sie|zapamieta_kontakt|zainteresowany|prosi_o_kontakt|przekazal_kontakt|chce_ai|odmowa|"
    "automat|oferta_pracy|inne\",\"termin_kontaktu\":\"kiedy osoba zapowiedziała kontakt, dosłownie, albo pusty\","
    "\"streszczenie\":\"2 zdania\",\"nastepny_krok\":\"co robimy i kiedy\",\"ocena\":0,"
    "\"miasto\":\"\",\"telefon\":\"\",\"email\":\"\",\"www\":\"\",\"charakterystyka\":\"3 zdania\"}.")

INSTRUKCJA_POCZTY = (
    "Dostajesz listę e-maili (id, nadawca, temat, fragment) oraz opisy projektów napisane przez właściciela. "
    "Przypisz każdy e-mail do projektu TYLKO wtedy, gdy pasuje do opisu projektu (osoba, adres lub firma). "
    "Wszystko inne to śmietnik. Odpowiedz WYŁĄCZNIE JSON-em: {\"wyniki\":[{\"id\":1,\"projekt\":\"klucz projektu albo smietnik\"}]} "
    "— dokładnie po jednym wpisie dla każdego id.")


def ustawienia() -> dict:
    try:
        porcja = max(1, min(50, int(store.ustawienie("porcja", "10"))))
    except ValueError:
        porcja = 10
    return {"model": store.ustawienie("model", ai.MODEL_DOMYSLNY),
            "prompt": store.ustawienie("prompt", "") or PROMPT_DOMYSLNY, "porcja": porcja,
            "prompt_detektyw": store.ustawienie("prompt_detektyw", "") or PROMPT_DETEKTYWA}


def przyjmij_odpowiedzi(lista: list[dict], ludzie: list[dict] | None = None) -> dict:
    t = w = 0
    for o in ludzie or []:
        nowa, dod = store.przyjmij_osobe(o)
        t += int(nowa)
        w += dod
    for o in lista:
        nowa, dod = store.przyjmij(o)
        t += int(nowa)
        w += dod
    return {"nowych_teczek": t, "nowych_wiadomosci": w}


def pobierz_z_kierownika() -> int:
    if not TOKEN_KIER:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    r = requests.get(f"{KIEROWNIK}/api/executor/replies", params={"unsent": 0},
                     headers={"X-Executor-Token": TOKEN_KIER}, timeout=60)
    r.raise_for_status()
    lista = r.json().get("odpowiedzi") or []
    przyjmij_odpowiedzi(lista)
    return len(lista)


def importuj_csv(raw: bytes, nowe_teczki: bool = False) -> dict:
    """messages.csv z archiwum LinkedIn („Pobierz kopię danych”): wszystkie rozmowy z treścią, w obie strony.

    Właściciel konta = najczęstszy nadawca. Teczkę zakładamy każdej osobie, która coś do nas napisała, a do której my
    wcześniej pisaliśmy (list/zaproszenie) — to są odpowiedzi na wiadomości sprzedażowe. Czy zostaje w teczkach, rozstrzyga prompt."""
    from collections import Counter, defaultdict
    wiersze = list(csv.reader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))
    hi = next((i for i, r in enumerate(wiersze) if any(c.strip().lower() == "from" for c in r)
               and any("sender" in c.lower() for c in r)), None)
    if hi is None:
        return {"error": "Nie znaleziono nagłówka messages.csv (FROM / SENDER PROFILE URL)."}
    nag = [c.strip().lower() for c in wiersze[hi]]
    idx = lambda f: next((i for i, c in enumerate(nag) if f(c)), None)
    i_from, i_su = idx(lambda c: c == "from"), idx(lambda c: "sender" in c and "url" in c)
    i_to, i_ru = idx(lambda c: c == "to"), idx(lambda c: "recipient" in c and "url" in c)
    i_date, i_txt = idx(lambda c: c == "date"), idx(lambda c: c == "content")
    if None in (i_su, i_ru, i_txt):
        return {"error": "W pliku brakuje kolumn SENDER PROFILE URL / RECIPIENT PROFILE URLS / CONTENT."}
    dane = [r for r in wiersze[hi + 1:] if len(r) > max(i_su, i_ru, i_txt)]
    wlasciciel = (Counter(r[i_su].strip().lower() for r in dane if r[i_su].strip()).most_common(1) or [("", 0)])[0][0]
    osoby = defaultdict(lambda: {"name": "", "od": [], "do": []})
    for r in dane:
        tekst = (r[i_txt] or "").strip()
        kiedy = r[i_date].strip() if i_date is not None and i_date < len(r) else ""
        if not tekst:
            continue
        su = r[i_su].strip()
        if su and su.lower() != wlasciciel:
            o = osoby[su]
            o["name"] = o["name"] or (r[i_from].strip() if i_from is not None else "")
            o["od"].append((kiedy, tekst))
        else:
            urls = [u.strip() for u in re.split(r"[;,\s]+", r[i_ru]) if "linkedin.com/" in u]
            imiona = [n.strip() for n in (r[i_to] if i_to is not None else "").split(",")]
            for k, u in enumerate(urls):
                if u.lower() != wlasciciel:
                    o = osoby[u]
                    o["name"] = o["name"] or (imiona[k] if len(imiona) == len(urls) else (imiona[0] if len(urls) == 1 else ""))
                    o["do"].append((kiedy, tekst))
    kandydaci = {u: o for u, o in osoby.items() if o["od"] and o["do"]}
    if not nowe_teczki:     # domyslnie tylko UZUPELNIAMY istniejace teczki (cala rozmowa w obie strony), bez zasypywania lista
        kandydaci = {u: o for u, o in osoby.items() if store.istnieje(u, o["name"])}
    teczek = wiadomosci = 0
    for u, o in kandydaci.items():
        historia = [{"ts": k, "kind": "letter" if "sigmaquality.pl" in x.lower() else "crm", "text": x} for k, x in o["do"]]
        if not o["od"]:                         # rozmowa bez odpowiedzi: dopisz same nasze wiadomosci
            store.przyjmij_osobe({"name": o["name"], "profile_url": u, "history": historia}, wymuszona=False)
        for k, x in o["od"]:
            nowa, dod = store.przyjmij({"name": o["name"], "profile_url": u, "history": historia, "received": k, "text": x})
            teczek += int(nowa)
            wiadomosci += dod
    return {"rozmow": len(osoby), "odpowiedzi_od_osob_do_ktorych_pisalismy": len(kandydaci),
            "nowych_teczek": teczek, "nowych_wiadomosci": wiadomosci}


def pobierz_ludzi_linkedin() -> int:
    """Osoby, o ktorych LinkedIn powiadomil, ze napisaly (Kierownik czyta je ze skrzynki) -- kazda dostaje teczke."""
    if not TOKEN_KIER:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    r = requests.get(f"{KIEROWNIK}/api/executor/linkedin-people", headers={"X-Executor-Token": TOKEN_KIER}, timeout=60)
    r.raise_for_status()
    ludzie = r.json().get("ludzie") or []
    for o in ludzie:
        store.przyjmij_osobe(o)
    return len(ludzie)


def odswiez_z_kierownika(limit: int = 120) -> int:
    """Dla teczek z listy dociaga z Kierownika poczte (wyslana i odebrana) oraz kalendarz — po nazwisku i adresie e-mail osoby."""
    if not TOKEN_KIER:
        return 0
    n = 0
    for t in [x for x in store.teczki() if (x["pozytywna"] or x["wymuszona"]) and not x["smietnik"]][:limit]:
        try:
            r = requests.get(f"{KIEROWNIK}/api/executor/person", params={"url": t["profil_url"], "name": t["nazwa"], "email": t["email"] if store._cudzy(t["email"]) else ""},
                             headers={"X-Executor-Token": TOKEN_KIER}, timeout=30)
            r.raise_for_status()
            o = r.json()
            if o.get("maile") or o.get("wydarzenia"):
                store.przyjmij_osobe({"name": t["nazwa"], "profile_url": t["profil_url"], "maile": o.get("maile"),
                                      "wydarzenia": o.get("wydarzenia")}, wymuszona=False)
                n += 1
        except Exception as e:
            log.warning("odswiez %s: %s", t["nazwa"], e)
    return n


def dodaj_po_adresach(adresy: list[str]) -> dict:
    """Wlasciciel wkleja adresy profili LinkedIn -- Analityk pyta Kierownika o wszystko, co o osobie wie, i zaklada teczki."""
    if not TOKEN_KIER:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    zalozone, nowe, nic, nowe_nazwy, istniejace = [], 0, [], [], []
    for url in adresy:
        url = url.strip().split("?")[0]
        if "linkedin.com/in/" not in url:
            continue
        r = requests.get(f"{KIEROWNIK}/api/executor/person", params={"url": url},
                         headers={"X-Executor-Token": TOKEN_KIER}, timeout=60)
        r.raise_for_status()
        o = r.json()
        if not o.get("name"):
            continue
        nowa, _ = store.przyjmij_osobe(o, jawnie=True)
        nowe += int(nowa)
        zalozone.append(o["name"])
        (nowe_nazwy if nowa else istniejace).append(o["name"])
        if not o.get("found"):
            nic.append(o["name"])
    return {"teczki": zalozone, "nowych": nowe, "nowe_nazwy": nowe_nazwy, "istniejace": istniejace, "bez_danych_w_kierowniku": nic}


def prompt_detektywa(t: dict) -> str:
    """Standardowy prompt dla detektywa z podstawionymi danymi osoby z teczki."""
    p = ustawienia()["prompt_detektyw"]
    for k, v in {"nazwisko": t["nazwa"], "stanowisko": t["stanowisko"] or "nieznane", "firma": t["firma"] or "nieznana",
                 "miasto": t["miasto"] or "nieznane", "linkedin": t["profil_url"] or "brak"}.items():
        p = p.replace("{" + k + "}", v)
    return p


def prompt_telefonu(t: dict) -> str:
    p = PROMPT_TELEFONU
    for k, v in {"nazwisko": t["nazwa"], "stanowisko": t["stanowisko"] or "nieznane", "firma": t["firma"] or "nieznana",
                 "miasto": t["miasto"] or "nieznane", "linkedin": t["profil_url"] or "brak"}.items():
        p = p.replace("{" + k + "}", v)
    return p


def zlec_rozmowy() -> dict:
    """Kierownik ma wyslac agenta GPT po pelne rozmowy z LinkedIn dla teczek, w ktorych nie ma tresci."""
    lista = store.bez_rozmowy()
    if not lista or not TOKEN_KIER:
        return {"zlecono": 0}
    r = requests.post(f"{KIEROWNIK}/api/executor/rozmowy-zlecenia", timeout=60, headers={"X-Executor-Token": TOKEN_KIER},
                      json={"osoby": [{"name": t["nazwa"], "profile_url": t["profil_url"], "thread_url": t["watek_url"]} for t in lista]})
    r.raise_for_status()
    return {"zlecono": len(lista), **r.json()}


def pobierz_poczte() -> int:
    if not TOKEN_KIER:
        raise RuntimeError("Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
    razem = 0
    while True:
        r = requests.get(f"{KIEROWNIK}/api/executor/mail", params={"after_id": store.ostatnie_id_poczty(), "limit": 500},
                         headers={"X-Executor-Token": TOKEN_KIER}, timeout=60)
        r.raise_for_status()
        lista = r.json().get("poczta") or []
        razem += store.przyjmij_poczte(lista)
        if len(lista) < 500:
            return razem


def klasyfikuj_poczte(limit: int = 100, paczka: int = 25) -> int:
    """Przypisuje maile do projektow wg promptow wlasciciela; reszta = smietnik. Bez promptow nic nie wchodzi do projektu."""
    ust = ustawienia()
    proj = {p["klucz"]: p for p in store.projekty() if p["prompt"].strip()}
    opisy = {k: p["prompt"].strip() for k, p in proj.items()}
    wsad = store.poczta_do_oceny(limit)
    if not wsad:
        return 0
    if not opisy:
        store.zapisz_projekty({m["id"]: "" for m in wsad})
        return len(wsad)
    zasady = "\n".join(f"PROJEKT {k} ({proj[k]['nazwa']}): {v}" for k, v in opisy.items())
    ok = 0
    for i in range(0, len(wsad), paczka):
        grupa = wsad[i:i + paczka]
        lista = [{"id": m["id"], "nadawca": m["nadawca"], "temat": m["temat"][:150], "fragment": m["tresc"][:250]} for m in grupa]
        r = ai.wyluskaj_json(ai.zapytaj(ust["model"], INSTRUKCJA_POCZTY + "\n\n" + zasady, json.dumps(lista, ensure_ascii=False), False))
        wyniki = {int(x["id"]): str(x.get("projekt") or "") for x in r.get("wyniki") or [] if str(x.get("id", "")).lstrip("-").isdigit()}
        store.zapisz_projekty({m["id"]: wyniki.get(m["id"], "") for m in grupa})
        ok += len(grupa)
    return ok


def _korespondencja(t: dict) -> str:
    return json.dumps({"osoba": t["nazwa"], "stanowisko_firma": t["naglowek"], "firma": t["firma"], "stanowisko": t["stanowisko"],
                       "profil_linkedin": t["profil_url"], "znane_miasto": t["miasto"],
                       "czy_wyslalismy_list": any(m["kierunek"] == "od_nas" for m in t["wiadomosci"]),
                       "korespondencja": [{"kierunek": m["kierunek"], "rodzaj": m["rodzaj"], "kiedy": m["kiedy"],
                                           "tekst": m["tekst"][:3000]} for m in t["wiadomosci"]]}, ensure_ascii=False)


def ocen_teczki(limit: int | None = None) -> tuple[int, int]:
    ust = ustawienia()
    ok = blad = 0
    for t in store.do_oceny(limit or ust["porcja"]):
        try:
            siec = bool(t["firma"] and (not t["miasto"] or not t["telefon"]))     # braki w danych firmy -> sprawdź w internecie
            r = ai.wyluskaj_json(ai.zapytaj(ust["model"], INSTRUKCJA + "\n\nKRYTERIA WŁAŚCICIELA (kiedy zakładamy teczkę):\n" + ust["prompt"],
                                            _korespondencja(t), siec))
            k = store.wyciagnij_kontakty(t["wiadomosci"])         # to, co osoba sama napisała, ma pierwszeństwo przed modelem
            for pole in ("telefon", "email"):
                if k[pole]:
                    r[pole] = k[pole]
            store.zapisz_ocene(t["id"], r, ust["model"])
            ok += 1
        except Exception as e:
            store.zapisz_blad(t["id"], f"{type(e).__name__}: {e}")
            blad += 1
            log.warning("ocena %s: %s", t["nazwa"], e)
    return ok, blad


def tick(zrodlo: str = "n8n", pobierz: bool = True) -> dict:
    """Pobierz z Kierownika (opcjonalnie) i oceń nowe/zmienione teczki. Naraz chodzi jeden przebieg."""
    if not _zamek.acquire(blocking=False):
        return {"ok": False, "uwaga": "inny przebieg jeszcze trwa"}
    try:
        wynik = {"pobrano": 0, "nowych_teczek": 0, "nowych_wiadomosci": 0, "ocenionych": 0, "bledow": 0, "uwaga": ""}
        if pobierz:
            try:
                przed = store.liczniki()
                wynik["pobrano"] = pobierz_z_kierownika()
                po = store.liczniki()
                wynik["nowych_teczek"] = po["teczek"] - przed["teczek"]
                wynik["nowych_wiadomosci"] = po["wiadomosci"] - przed["wiadomosci"]
            except Exception as e:
                wynik["uwaga"] = f"Kierownik: {type(e).__name__}: {str(e)[:150]}"
        if pobierz:
            try:
                wynik["maile_teczek"] = odswiez_z_kierownika()
            except Exception as e:
                wynik["uwaga"] += f" Poczta teczek: {type(e).__name__}: {str(e)[:100]}"
            # zlecanie agentowi GPT przepisywania rozmów wyłączone: agent robi tylko zaproszenia, listy i skrzynkę
            try:
                wynik["ludzie_linkedin"] = pobierz_ludzi_linkedin()
            except Exception as e:
                wynik["uwaga"] += f" Ludzie z LinkedIn: {type(e).__name__}: {str(e)[:120]}"
            try:
                wynik["poczta_nowa"] = pobierz_poczte()
            except Exception as e:
                wynik["uwaga"] += f" Poczta: {type(e).__name__}: {str(e)[:120]}"
        if pobierz:
            try:
                import leady                        # 18.10: zamiast „zaległych leadów” — w nocy kolejka leadów do listów dla Kierownika (w tle)
                wynik["zalegle"] = leady.w_nocy()
            except Exception as e:
                wynik["uwaga"] += f" Leady do listów: {type(e).__name__}: {str(e)[:120]}"
        if pobierz:
            try:
                import branze                       # szufladki branzowe: ilu VIP-ow zaproszonych i ilu juz w kontaktach
                branze.odswiez_wszystkie()
            except Exception as e:
                wynik["uwaga"] += f" Branże: {type(e).__name__}: {str(e)[:100]}"
        try:
            wynik["scalone"] = len(store.scal_duplikaty())             # ta sama osoba pod kilkoma adresami profilu = jedna teczka
        except Exception as e:
            wynik["uwaga"] += f" Scalanie duplikatów: {type(e).__name__}: {str(e)[:100]}"
        if not ai.wlaczone():
            wynik["uwaga"] += " Brak OPENAI_API_KEY — ocena wyłączona."
        else:
            for _ in range(8):                     # do 8 porcji, az wszystkie teczki maja decyzje
                ok, bl = ocen_teczki()
                wynik["ocenionych"] += ok
                wynik["bledow"] += bl
                if not store.liczniki()["do_oceny"] or (ok == 0):
                    break
            try:
                wynik["poczta_przypisana"] = klasyfikuj_poczte()
            except Exception as e:
                wynik["uwaga"] += f" Projekty: {type(e).__name__}: {str(e)[:120]}"
        if ai.wlaczone():
            import strateg
            threading.Thread(target=strateg.szybki_przeglad, daemon=True).start()    # nowe odpowiedzi z dnia: ocena, alarm, lista pilnych
        wynik.setdefault("poczta_nowa", 0)
        wynik.setdefault("poczta_przypisana", 0)
        zapis = {k: v for k, v in wynik.items() if k not in ("poczta_nowa", "poczta_przypisana", "ludzie_linkedin", "zlecenia", "maile_teczek", "scalone", "zalegle")}
        zapis["uwaga"] = (zapis["uwaga"] + f" poczta: nowych {wynik['poczta_nowa']}, ocenionych {wynik['poczta_przypisana']}").strip()
        return {"ok": True, **store.zakoncz_przebieg(zrodlo, **zapis), **wynik, **store.liczniki(), **store.licznik_poczty()}
    finally:
        _zamek.release()
