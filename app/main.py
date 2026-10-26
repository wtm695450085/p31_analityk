"""Analityk (analityk.sigmaquality.pl): zaklada teczki osob, ktore odpisaly na listy z LinkedIn. agent_Darwin = workflow n8n -> /api/hermes/tick."""
import hmac
import logging
import os
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

import ai
import nadzorca
import store
import strateg
import branze
import leady
import zalegle
from render import strona, strona_branz, strona_odprawy, strona_szuflady, strona_teczki

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
STATIC = Path(__file__).parent / "static"
HERMES_TOKEN = os.getenv("HERMES_TOKEN", "")
app = FastAPI(title="Analityk", docs_url="/api/docs", redoc_url=None)


@app.on_event("startup")
def _start():
    store.init()
    branze.init()
    leady.init()


def hermes_auth(x_hermes_token: str = Header("")):
    if not HERMES_TOKEN or not hmac.compare_digest(x_hermes_token, HERMES_TOKEN):
        raise HTTPException(401, "Zły token agent_Darwin")


@app.get("/", response_class=HTMLResponse)
def index(info: str = ""):
    return HTMLResponse(strona(info), headers={"Cache-Control": "no-store"})


@app.post("/ui/ustawienia")
def ui_ustawienia(model: str = Form(...), porcja: str = Form("10"), prompt: str = Form(""), analizuj: str = Form(""),
                  prompt_detektyw: str = Form(""), silnik: str = Form("")):
    if silnik in ("api", "sdk"):
        store.ustaw("silnik", silnik)
    stare = nadzorca.ustawienia()
    if prompt.strip() != stare["prompt"]:
        store.przelicz_teczki()          # nowe kryteria = nowa decyzja o kazdej teczce
    store.ustaw("model", model)
    store.ustaw("porcja", porcja)
    store.ustaw("prompt", prompt.strip() if prompt.strip() != nadzorca.PROMPT_DOMYSLNY else "")
    store.ustaw("prompt_detektyw", prompt_detektyw.strip() if prompt_detektyw.strip() != nadzorca.PROMPT_DETEKTYWA else "")
    if analizuj:
        threading.Thread(target=nadzorca.tick, args=("ręcznie",), daemon=True).start()
        return RedirectResponse("/?info=Analiza+ruszyła+w+tle+—+odśwież+stronę+za+chwilę", status_code=303)
    return RedirectResponse("/?info=Zapisano", status_code=303)


@app.post("/ui/projekty")
async def ui_projekty(request: Request):
    """Zapis promptow wszystkich projektow poczty (pola prompt__<klucz>)."""
    f = await request.form()
    prompty = {k[len("prompt__"):]: str(v) for k, v in f.items() if k.startswith("prompt__")}
    if store.zapisz_prompty_projektow(prompty):
        store.przelicz_poczte()
    return RedirectResponse("/?info=Zapisano+projekty#projekty", status_code=303)


@app.post("/ui/projekt-nowy")
def ui_projekt_nowy(nazwa: str = Form(...), rodzaj: str = Form("projekt")):
    k = store.dodaj_projekt(nazwa, rodzaj)
    return RedirectResponse("/?info=" + ("Dodano+projekt" if k else "Podaj+nazwę+projektu") + "#projekty", status_code=303)


@app.post("/ui/projekt-usun/{klucz}")
def ui_projekt_usun(klucz: str):
    store.usun_projekt(klucz)
    return RedirectResponse("/?info=Projekt+usunięty#projekty", status_code=303)


KIEROWNIK_TOKEN = os.getenv("KIEROWNIK_PUSH_TOKEN", "")


def kierownik_auth(x_kierownik_token: str = Header("")):
    if not KIEROWNIK_TOKEN or not hmac.compare_digest(x_kierownik_token, KIEROWNIK_TOKEN):
        raise HTTPException(401, "Zły token Kierownika")


@app.get("/api/kierownik/leady-stan", dependencies=[Depends(kierownik_auth)])
def kierownik_leady_stan():
    """Dla tablicy Kierownika: ile osób Analityk ocenił, ile zakwalifikował, ile odrzucił, kiedy był ostatni przebieg."""
    leady.init()
    with store.conn() as c:
        nie_ok = c.execute("SELECT COUNT(*) n FROM leady_oceny WHERE ok=0").fetchone()["n"]
    u = leady.ustawienia()
    return {**leady.liczniki_ocen(), "odrzuconych": nie_ok, "ostatni": leady.ostatni(), "cel": u["cel"], "prog": u["prog"]}


@app.post("/api/kierownik/odpowiedzi", dependencies=[Depends(kierownik_auth)])
def kierownik_odpowiedzi(payload: dict = Body(...)):
    """Kierownik wysyla wszystkie odpowiedzi z LinkedIn; zakladamy teczki, ocena rusza w tle."""
    w = nadzorca.przyjmij_odpowiedzi(payload.get("odpowiedzi") or [], payload.get("ludzie") or [])
    threading.Thread(target=nadzorca.tick, args=("Kierownik", False), daemon=True).start()
    return {"ok": True, **w, **store.liczniki()}


@app.post("/api/kierownik/dialogi", dependencies=[Depends(kierownik_auth)])
def kierownik_dialogi(payload: dict = Body(...)):
    """Kierownik przekazuje dialogi z LinkedIn przepisane przez agenta (obie strony) — wkladamy je w wlasciwe teczki, a teczki dostaja ocene."""
    nowe = wiad = pominiete = 0
    for d in payload.get("dialogi") or []:
        n, w = store.przyjmij_dialog(d)
        nowe += int(n)
        wiad += w
        pominiete += int(not n and not w)
    if nowe or wiad:
        threading.Thread(target=nadzorca.tick, args=("dialogi od agenta", False), daemon=True).start()
    return {"ok": True, "nowych_teczek": nowe, "nowych_wiadomosci": wiad, "pominietych_dialogow": pominiete}


@app.post("/ui/import")
async def ui_import(plik: UploadFile = File(...), nowe: str = Form("")):
    """messages.csv z archiwum LinkedIn -> teczki; ocena wg promptu rusza w tle."""
    w = nadzorca.importuj_csv(await plik.read(), bool(nowe))
    if "error" in w:
        return RedirectResponse("/?info=" + w["error"].replace(" ", "+"), status_code=303)
    threading.Thread(target=nadzorca.tick, args=("import CSV", False), daemon=True).start()
    return RedirectResponse(f"/?info=Import:+uzupełniono+{w['odpowiedzi_od_osob_do_ktorych_pisalismy']}+teczek+({w['nowych_wiadomosci']}+nowych+wiadomości),+nowych+teczek+{w['nowych_teczek']}", status_code=303)


WYWIAD_TOKEN = os.getenv("WYWIAD_TOKEN", "")


def wywiad_auth(x_wywiad_token: str = Header("")):
    if not WYWIAD_TOKEN or not hmac.compare_digest(x_wywiad_token, WYWIAD_TOKEN):
        raise HTTPException(401, "Zły token Wywiadowcy")


@app.post("/api/wywiad/leady", dependencies=[Depends(wywiad_auth)])
def wywiad_leady(payload: dict = Body(...)):
    """Wywiadowca -> zielone teczki + zlecenia dla detektywa (namierzenie w LinkedIn)."""
    nowe = zlecen = 0
    for l in payload.get("leady") or []:
        n, z = store.przyjmij_lead_wywiadu(l)
        nowe += n
        zlecen += z
    return {"ok": True, "nowych_teczek": nowe, "zlecen_detektywa": zlecen}


@app.post("/ui/teczka-url")
def ui_teczka_url(adresy: str = Form(...)):
    """Wklejone adresy profili LinkedIn -> teczki z danymi z Kierownika."""
    import re as _re
    w = nadzorca.dodaj_po_adresach([a for a in _re.split(r"[\s,;]+", adresy) if a])
    threading.Thread(target=nadzorca.tick, args=("adresy LinkedIn", False), daemon=True).start()
    cz = []
    if w.get("nowe_nazwy"):
        cz.append("Założono nowe teczki: " + ", ".join(w["nowe_nazwy"]))
    if w.get("istniejace"):
        cz.append("Te teczki już istnieją (uzupełniono dane): " + ", ".join(w["istniejace"]))
    info = ". ".join(cz) if cz else "Nie rozpoznano adresów LinkedIn"
    return RedirectResponse("/?info=" + info.replace(" ", "+"), status_code=303)


@app.post("/api/teczka-url", dependencies=[Depends(hermes_auth)])
def api_teczka_url(payload: dict = Body(...)):
    return nadzorca.dodaj_po_adresach(payload.get("adresy") or [])


@app.post("/ui/teczka-nowa")
def ui_teczka_nowa(name: str = Form(...), profile_url: str = Form(""), firma: str = Form(""), stanowisko: str = Form(""),
                   od_niego: str = Form(""), ode_mnie: str = Form("")):
    store.przyjmij_osobe({"name": name, "profile_url": profile_url.strip(), "firma": firma, "stanowisko": stanowisko,
                          "wiadomosci": [{"kierunek": "od_leada", "tekst": od_niego}, {"kierunek": "od_nas", "tekst": ode_mnie}]}, jawnie=True)
    threading.Thread(target=nadzorca.tick, args=("ręcznie", False), daemon=True).start()
    return RedirectResponse("/?info=Teczka+założona", status_code=303)


@app.post("/ui/teczka/{tid}/wiadomosc")
def ui_dopisz(tid: int, typ: str = Form("od_leada|wiadomość LinkedIn"), tekst: str = Form(""), data: str = Form(""),
              godzina: str = Form("")):
    kierunek, _, rodzaj = typ.partition("|")
    kiedy = (f"{data.strip()} {godzina.strip()}".strip() if data.strip() else "")
    store.dopisz_wiadomosc(tid, kierunek, tekst, kiedy, rodzaj or "wklejone")
    threading.Thread(target=nadzorca.tick, args=("ręcznie", False), daemon=True).start()
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/detektyw")
def ui_detektyw(tid: int, prompt: str = Form(...)):
    """Zlecenie dla detektywa: znajdz kontakt do osoby z teczki. Aplikacja detektywa jeszcze nie istnieje — zlecenie czeka w kolejce."""
    store.dodaj_zlecenie(tid, prompt)
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/detektyw-telefon")
def ui_detektyw_telefon(tid: int):
    """Zlecenie dla detektywa: znajdz TYLKO numer telefonu tej osoby (nic wiecej)."""
    t = store.teczka(tid)
    if not t:
        raise HTTPException(404, "Nie ma takiej teczki")
    store.dodaj_zlecenie(tid, nadzorca.prompt_telefonu(t), "telefon")
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


DETEKTYW_TOKEN = os.getenv("DETEKTYW_TOKEN", "") or HERMES_TOKEN


def detektyw_auth(x_detektyw_token: str = Header("")):
    if not DETEKTYW_TOKEN or not hmac.compare_digest(x_detektyw_token, DETEKTYW_TOKEN):
        raise HTTPException(401, "Zły token detektywa")


@app.get("/api/detektyw/zlecenia", dependencies=[Depends(detektyw_auth)])
def api_detektyw_zlecenia():
    """Dla przyszłej aplikacji detektywa: otwarte zlecenia z danymi osoby i promptem."""
    return {"zlecenia": store.zlecenia_otwarte()}


@app.post("/api/detektyw/wynik-osoby", dependencies=[Depends(detektyw_auth)])
def api_detektyw_wynik_osoby(payload: dict = Body(...)):
    """Detektyw odsyła wynik dla osoby z listy Wywiadowcy: {nazwa, wynik, linkedin_url?, telefon?, email?, miasto?, www?}."""
    if not store.wynik_detektywa_osoby(payload):
        raise HTTPException(400, "Brak imienia i nazwiska")
    return {"ok": True}


@app.post("/api/detektyw/vipy", dependencies=[Depends(detektyw_auth)])
def api_detektyw_vipy(payload: dict = Body(...)):
    """VIP-y z listy firm (Detektyw: zlecenie na firmy): zakladamy teczki z adresem LinkedIn i przekazujemy je Kierownikowi,
    ktory da je agentowi GPT jako osoby do zaproszenia / listu. Gdy Kierownik nie odpowie, zwracamy 502 — Detektyw ponowi."""
    import requests
    vipy = [v for v in payload.get("vipy") or [] if "linkedin.com/in/" in str(v.get("linkedin_url") or "").lower()
            and len(str(v.get("nazwa") or "").split()) >= 2]
    leady = []
    for v in vipy:
        store.wynik_detektywa_osoby({"nazwa": v["nazwa"], "firma": v.get("firma"), "stanowisko": v.get("stanowisko"), "miasto": v.get("miasto"),
                                     "linkedin_url": v["linkedin_url"], "vip": True, "zaangazowanie": 5,
                                     "wynik": f"Detektyw (zlecenie na firmy): VIP z firmy {v.get('firma') or '—'} — profil LinkedIn {v['linkedin_url']}."})
        szuf = branze.szuflada(int(v.get("szuflada") or 0)) if v.get("szuflada") else None
        if szuf:
            branze.zapisz_vipa(szuf["id"], {**v})
        leady.append({"name": v["nazwa"], "linkedin_url": v["linkedin_url"], "company": v.get("firma") or "", "position": v.get("stanowisko") or "",
                      "city": v.get("miasto") or "", "engagement": 5, "why": "VIP z listy firm (Detektyw)",
                      **({"szuflada": branze.etykieta(szuf)} if szuf else {})})
    dodano = 0
    if leady:
        if not nadzorca.TOKEN_KIER:
            raise HTTPException(500, "Brak KIEROWNIK_EXECUTOR_TOKEN w .env")
        try:
            r = requests.post(f"{nadzorca.KIEROWNIK}/api/executor/vip", json={"leady": leady}, timeout=60,
                              headers={"X-Executor-Token": nadzorca.TOKEN_KIER})
            r.raise_for_status()
            dodano = (r.json().get("added") or 0)
        except Exception as e:
            raise HTTPException(502, f"Kierownik nie przyjął VIP-ów: {str(e)[:160]}")
    return {"ok": True, "teczki": len(vipy), "nowych_u_kierownika": dodano}


@app.post("/api/detektyw/wynik", dependencies=[Depends(detektyw_auth)])
def api_detektyw_wynik(payload: dict = Body(...)):
    """Detektyw odsyła wynik: {id, wynik, telefon?, email?, miasto?, www?}."""
    if not store.zapisz_wynik_detektywa(int(payload.get("id", 0)), payload.get("wynik") or "", payload):
        raise HTTPException(404, "Nie ma takiego zlecenia")
    return {"ok": True}


@app.post("/ui/teczka/{tid}/dane")
def ui_dane(tid: int, miasto: str = Form(""), telefon: str = Form(""), email: str = Form(""), www: str = Form(""),
            firma: str = Form(""), stanowisko: str = Form(""), nazwa: str = Form(None), profil_url: str = Form(None),
            watek_url: str = Form(None), charakterystyka: str = Form(None)):
    store.zapisz_dane(tid, miasto, telefon, email, www, firma, stanowisko, nazwa, profil_url, watek_url, charakterystyka)
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/ocena")
def ui_ocena(tid: int, ocena: str = Form("")):
    store.ustaw_ocene(tid, int(ocena) if ocena.strip().isdigit() else None)
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/wiadomosc/{mid}/edytuj")
def ui_wiadomosc_edytuj(mid: int, typ: str = Form("zdarzenie|notatka"), tekst: str = Form(""), data: str = Form(""), godzina: str = Form("")):
    kierunek, _, rodzaj = typ.partition("|")
    tid = store.edytuj_wiadomosc(mid, kierunek, rodzaj, data, godzina, tekst)
    if tid is None:
        raise HTTPException(404, "Nie ma takiego wpisu albo nie jest Twój")
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/wiadomosc/{mid}/usun")
def ui_wiadomosc_usun(mid: int):
    tid = store.usun_wiadomosc(mid)
    if tid is None:
        raise HTTPException(404, "Nie ma takiego wpisu albo nie jest Twój")
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.get("/btn-{nazwa}.png")
def przycisk_obrazkowy(nazwa: str):
    if nazwa not in ("wyslij", "telefon", "przypisz", "zaloz", "wroc", "zaloz-inic", "przypisz-inic"):
        raise HTTPException(404, "Nie ma takiego przycisku")
    return FileResponse(STATIC / f"btn-{nazwa}.png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/ikona-teczki.png")
def ikona_teczki():
    return FileResponse(STATIC / "ikona-teczki.png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/ikona-kosz.png")
def ikona_kosz():
    return FileResponse(STATIC / "ikona-kosz.png", headers={"Cache-Control": "public, max-age=300"})


@app.post("/ui/teczka/{tid}/zaloz")
def ui_teczka_zaloz(tid: int, rodzaj: str = Form(...), nazwa: str = Form(...)):
    """Zaklada projekt (czerwony) albo inicjatywe (rozowa) z tej teczki i przypisuje do niej teczke."""
    k = store.dodaj_projekt(nazwa, rodzaj)
    if k:
        store.przypisz_teczke(tid, k)
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/przypisz")
def ui_teczka_przypisz(tid: int, klucz: str = Form("")):
    store.przypisz_teczke(tid, klucz)
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/przejrzana")
def ui_teczka_przejrzana(tid: int, wartosc: str = Form("1")):
    store.ustaw_przejrzana(tid, wartosc == "1")
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/wysoka")
def ui_teczka_wysoka(tid: int, wartosc: str = Form("1")):
    store.ustaw_wysoka(tid, wartosc == "1")
    return RedirectResponse(f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/pilna")
def ui_teczka_pilna(tid: int, wartosc: str = Form("1"), wroc: str = Form("")):
    store.ustaw_pilna(tid, wartosc == "1")
    return RedirectResponse("/" if wroc == "lista" else f"/teczka/{tid}", status_code=303)


@app.post("/ui/teczka/{tid}/kasuj")
def ui_kasuj(tid: int):
    store.kasuj(tid)
    return RedirectResponse("/?info=Teczka+skasowana", status_code=303)


@app.post("/api/kierownik/rozmowy", dependencies=[Depends(kierownik_auth)])
def kierownik_rozmowy(payload: dict = Body(...)):
    """Agent GPT przepisał z LinkedIn pełne rozmowy; Kierownik przysyła je do teczek."""
    n = 0
    for r in payload.get("rozmowy") or []:
        if (r.get("text") or "").strip():
            store.przyjmij_osobe({"name": r.get("name"), "profile_url": r.get("profile_url") or "",
                                  "wiadomosci": [{"kierunek": "rozmowa", "kiedy": store.teraz()[:10], "tekst": r["text"]}]},
                                 wymuszona=False, jawnie=True)
            n += 1
    threading.Thread(target=nadzorca.tick, args=("rozmowy od agenta", False), daemon=True).start()
    return {"ok": True, "teczek": n}


@app.post("/ui/zalegle")
def ui_zalegle(ile: str = Form("10")):
    try:
        store.ustaw("zalegle_ile", str(max(1, min(30, int(ile or 10)))))
        w = zalegle.przygotuj(wymus=True)
        info = f"Kierownik dostał {w['wyslano_do_kierownika']} zaległych leadów (wszystkich luk: {w['luk']})"
    except Exception as e:
        info = f"Błąd listy zaległych: {e}"
    return RedirectResponse("/?info=" + info.replace(" ", "+"), status_code=303)


@app.post("/ui/leady")
def ui_leady(silnik: str = Form("api"), model: str = Form(""), model_sdk: str = Form(""), cel: str = Form("150"), minuty: str = Form("40"),
             porcja: str = Form("40"), godzina: str = Form("1"), prompt: str = Form(""), teraz: str = Form("")):
    store.ustaw("leady_silnik", "sdk" if silnik == "sdk" else "api")
    store.ustaw("leady_model", model.strip() or ai.MODEL_DOMYSLNY)
    store.ustaw("leady_model_sdk", model_sdk.strip())
    for k, v in (("leady_cel", cel), ("leady_minuty", minuty), ("leady_porcja", porcja), ("leady_godzina", godzina)):
        if v.strip().isdigit():
            store.ustaw(k, v.strip())
    store.ustaw("leady_prompt", prompt.strip() if prompt.strip() != leady.PROMPT_DOMYSLNY else "")
    if teraz:
        info = "Szukanie leadów ruszyło w tle — odśwież stronę za kilka minut" if leady.uruchom_teraz() else "Szukanie leadów już trwa"
    else:
        info = "Zapisano ustawienia leadów"
    return RedirectResponse("/?info=" + info.replace(" ", "+"), status_code=303)


@app.post("/ui/zlec-rozmowy")
def ui_zlec_rozmowy():
    try:
        w = nadzorca.zlec_rozmowy()
        info = f"Kierownik dostał zlecenie: {w.get('zlecono', 0)} rozmów do przepisania przez agenta GPT"
    except Exception as e:
        info = f"Błąd zlecenia: {e}"
    return RedirectResponse("/?info=" + info.replace(" ", "+"), status_code=303)


@app.get("/teczka/{tid}", response_class=HTMLResponse)
def widok_teczki(tid: int):
    t = store.teczka(tid)
    if not t:
        raise HTTPException(404, "Nie ma takiej teczki")
    return HTMLResponse(strona_teczki(t), headers={"Cache-Control": "no-store"})


@app.get("/api/teczki")
def api_teczki():
    return store.teczki()


def _info(url: str, tekst: str) -> RedirectResponse:
    return RedirectResponse(url + ("&" if "?" in url else "?") + "info=" + quote(tekst), status_code=303)


@app.get("/branze", response_class=HTMLResponse)
def branze_strona(info: str = ""):
    return HTMLResponse(strona_branz(info), headers={"Cache-Control": "no-store"})


@app.post("/ui/branze/nowa")
def ui_branze_nowa(branza: str = Form(""), rejon: str = Form("")):
    try:
        sid = branze.utworz(branza, rejon)
    except ValueError as e:
        return _info("/branze", str(e))
    return _info(f"/branze/{sid}", "Szufladka założona — wrzuć do niej plik z firmami")


@app.get("/branze/{sid}", response_class=HTMLResponse)
def branze_szuflada(sid: int, info: str = "", status: str = ""):
    if not branze.szuflada(sid):
        raise HTTPException(404, "Nie ma takiej szufladki")
    return HTMLResponse(strona_szuflady(sid, info, status), headers={"Cache-Control": "no-store"})


@app.post("/ui/branze/{sid}/wrzuc")
async def ui_branze_wrzuc(sid: int, pliki: list[UploadFile] = File(...)):
    if not branze.szuflada(sid):
        raise HTTPException(404, "Nie ma takiej szufladki")
    ok, bl, nowe = [], [], 0
    for f in pliki:
        try:
            nowe += branze.wrzuc(sid, f.filename or "", await f.read())
            ok.append(f.filename)
        except ValueError as e:
            bl.append(str(e))
    info = (f"Wczytano {len(ok)} plik(ów), nowych firm: {nowe}. " if ok else "") + ("Odrzucono: " + "; ".join(bl) if bl else "")
    return _info(f"/branze/{sid}", info.strip())


@app.post("/ui/branze/{sid}/szukaj")
def ui_branze_szukaj(sid: int):
    try:
        w = branze.zlec_detektywowi(sid)
    except Exception as e:
        return _info(f"/branze/{sid}", f"Nie udało się zlecić Detektywowi: {str(e)[:200]}")
    return _info(f"/branze/{sid}", w["uwaga"] or f"Zlecono Detektywowi {w['wyslano']} firm — szuka sam, VIP-y pojawią się tu i pójdą do Kierownika")


@app.post("/ui/branze/{sid}/odswiez")
def ui_branze_odswiez(sid: int):
    try:
        w = branze.odswiez_statusy(sid)
    except Exception as e:
        return _info(f"/branze/{sid}", f"Nie udało się odświeżyć statusów: {str(e)[:200]}")
    return _info(f"/branze/{sid}", f"Odświeżono statusy ({w['sprawdzono']} VIP-ów)")


@app.post("/ui/branze/{sid}/specjalna")
def ui_branze_specjalna(sid: int, prompt: str = Form(""), vip: list[int] = Form([]), jeden: int = Form(0), akcja: str = Form("zapisz")):
    """Prompt specjalnej procedury (zapis) i jej wysylka: zaznaczeni VIP-y albo jeden (przycisk w wierszu)."""
    if not branze.szuflada(sid):
        raise HTTPException(404, "Nie ma takiej szufladki")
    branze.zapisz_prompt_specjalny(sid, prompt)
    if akcja == "zapisz" and not jeden:
        return _info(f"/branze/{sid}?status=kontakty", "Prompt specjalnej procedury zapisany")
    try:
        w = branze.wyslij_specjalnie(sid, [jeden] if jeden else vip)
    except Exception as e:
        return _info(f"/branze/{sid}?status=kontakty", f"Nie wysłano: {str(e)[:200]}")
    return _info(f"/branze/{sid}?status=kontakty", f"Specjalna procedura: przekazano Kierownikowi {w['wyslano']} os. (komenda „/spec N” w czacie je wyśle)" + (f"; pominięto {w['duplikaty']} os., które dostały już ten list z innej szufladki" if w["duplikaty"] else ""))


@app.post("/ui/branze/{sid}/usun")
def ui_branze_usun(sid: int):
    branze.usun_szuflade(sid)
    return _info("/branze", "Szufladka usunięta (pliki zostały w katalogu danych)")


@app.get("/branze/{sid}/vipy.csv")
def branze_vipy_csv(sid: int, status: str = ""):
    import csv, io
    s = branze.szuflada(sid)
    if not s:
        raise HTTPException(404, "Nie ma takiej szufladki")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["imie_nazwisko", "firma", "stanowisko", "linkedin", "zaproszony", "w_kontaktach"])
    for v in branze.vipy(sid, status):
        w.writerow([v["nazwa"], v["firma"], v["stanowisko"], v["linkedin_url"], "tak" if v["zaproszony"] else "nie", "tak" if v["w_kontaktach"] else "nie"])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="vipy-{sid}.csv"'})


@app.get("/odprawa", response_class=HTMLResponse)
def odprawa(info: str = ""):
    return HTMLResponse(strona_odprawy(info), headers={"Cache-Control": "no-store"})


@app.post("/ui/odprawa")
def ui_odprawa():
    r = strateg.uruchom("ręcznie")
    return RedirectResponse("/odprawa?info=" + ("Odprawa+ruszyła" if r["ok"] else r["uwaga"].replace(" ", "+")), status_code=303)


@app.post("/ui/odprawa/ustawienia")
def ui_odprawa_ustawienia(model: str = Form(...), kontekst: str = Form(""), silnik: str = Form(""), model_sdk_odprawa: str = Form("")):
    if model_sdk_odprawa in ai.SDK_MODELE:
        store.ustaw("model_sdk_odprawa", model_sdk_odprawa)
    if silnik in ("api", "sdk"):
        store.ustaw("silnik", silnik)
    store.ustaw("model_strateg", model)
    store.ustaw("kontekst_strateg", kontekst.strip() if kontekst.strip() != strateg.KONTEKST_DOMYSLNY else "")
    return RedirectResponse("/odprawa?info=Zapisano", status_code=303)


@app.post("/api/hermes/odprawa", dependencies=[Depends(hermes_auth)])
def hermes_odprawa():
    """Np. workflow n8n w niedziele wieczorem: plan na poniedzialek gotowy rano."""
    return strateg.uruchom("n8n")


@app.post("/api/hermes/tick", dependencies=[Depends(hermes_auth)])
def hermes_tick():
    return nadzorca.tick("n8n")


@app.get("/api/health")
def health():
    return {"ok": True, "ai": ai.wlaczone(), **store.liczniki()}


@app.get("/analityczka.png")
def obraz():
    return FileResponse(STATIC / "analityczka.png", headers={"Cache-Control": "public, max-age=300"})


@app.get("/ikona.png")
@app.get("/favicon.ico")
def ikona():
    return FileResponse(STATIC / "ikona.png", media_type="image/png", headers={"Cache-Control": "public, max-age=300"})
