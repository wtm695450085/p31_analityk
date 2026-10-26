"""Strona Analityka: ustawienia (model, polecenie), status Agenta i lista leadow z analiza."""
import html
from datetime import datetime

import ai
import nadzorca
import store
import strateg
import branze

TYTUL = "Analityk — teczki klientów"


def e(t) -> str:
    return html.escape(str(t if t is not None else ""), quote=True)


CSS = """
:root{--tlo:#fff;--tekst:#111;--slaby:#5b5b5b;--linia:#d9d9d9;--pole:#f7f7f7;--ok:#17703f;--zle:#a32020;
 --sans:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--tlo);color:var(--tekst);font:15px/1.55 var(--sans)}
.wrap{max-width:1500px;margin:0 auto;padding:22px 20px 60px}
header{border-bottom:2px solid var(--tekst);padding-bottom:10px;margin-bottom:16px}
header h1{margin:0;font-size:21px}header h1 img{width:34px;height:34px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:10px}
.pod{color:var(--slaby);font-size:13px}
.uklad{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:22px;align-items:start}
aside{position:sticky;top:14px;border:1px solid var(--linia);border-radius:14px;padding:14px 12px;text-align:center;
 background:linear-gradient(#fbfaf6,#f1ede2);box-shadow:0 2px 8px rgba(0,0,0,.08)}
aside img{width:100%;height:auto;display:block;filter:drop-shadow(0 4px 6px rgba(0,0,0,.2))}
aside .podp{margin-top:10px;font-weight:600;font-size:13px}
.kafle{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
.kafel{border:1px solid var(--linia);border-radius:10px;padding:10px 12px}.kafel b{display:block;font-size:26px}
.kafel span{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--slaby)}
.panel{border:1px solid var(--linia);border-top:3px solid var(--ok);border-radius:10px;padding:16px 18px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.panel h2{margin:0 0 12px;font-size:18px}
.siatka{display:grid;grid-template-columns:1fr 1fr;gap:14px}
label.pl{display:block;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--slaby);font-weight:600;margin:0 0 6px}
select,input[type=number],textarea{font:inherit;width:100%;padding:8px 10px;border:1px solid var(--linia);border-radius:8px;background:var(--pole)}
textarea{min-height:110px;resize:vertical}
.akcje{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px}
button{font:inherit;padding:10px 18px;border-radius:8px;border:1px solid var(--tekst);background:#fff;cursor:pointer}
button.glowny{background:var(--ok);border-color:var(--ok);color:#fff;font-weight:700;font-size:16px;padding:13px 26px;box-shadow:0 2px 6px rgba(23,112,63,.35)}
.male{color:var(--slaby);font-size:12.5px}
.lead{border:1px solid var(--linia);border-left:3px solid var(--tekst);border-radius:8px;padding:12px 16px;margin:0 0 10px;display:grid;grid-template-columns:minmax(0,1fr) 130px;gap:14px}
.lead .poz{text-align:right}.lead .poz b{font-size:28px;display:block;line-height:1.1}
.pasek{display:inline-flex;gap:2px;vertical-align:middle}.pasek i{width:11px;height:16px;border:1px solid var(--tekst);display:block}.pasek i.w{background:var(--tekst)}
.et{display:inline-block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;border:1px solid var(--linia);border-radius:4px;padding:0 6px;margin-left:6px}
.et.wysoki{border-color:var(--ok);color:var(--ok);font-weight:700}
.lead dl{margin:6px 0 0;display:grid;grid-template-columns:150px 1fr;gap:3px 12px;font-size:14px}.lead dt{color:var(--slaby)}.lead dd{margin:0}
.zle{color:var(--zle)}
.zielona{border-left:8px solid #2e9e57!important;background:#eaf7ef!important}
.szara{border-left:8px solid #8a8a8a!important;background:#ececec!important;color:#555}
.img-btn{display:inline-block;padding:0;border:0;background:none;cursor:pointer;flex:none;transition:transform .12s,filter .12s}
.img-btn img{height:60px;width:auto;display:block;filter:drop-shadow(0 3px 4px rgba(0,0,0,.35))}
.img-btn:hover{transform:scale(1.04);filter:brightness(1.1)}.img-btn[disabled]{opacity:.45;cursor:not-allowed;filter:grayscale(.6)}
.ikona-btn{display:inline-block;width:96px;height:96px;padding:0;border:0;background:none;cursor:pointer;flex:none;transition:transform .12s,filter .12s}
.ikona-btn img{width:100%;height:100%;display:block;filter:drop-shadow(0 3px 5px rgba(0,0,0,.35))}
.ikona-btn:hover{transform:scale(1.07);filter:brightness(1.1)}
.ikony-bok{display:flex;justify-content:space-around;align-items:center;margin-top:18px}.ikony-bok form{margin:0}
.edyt{margin-top:6px;font-size:12px}.edyt summary{cursor:pointer;color:var(--slaby)}.edyt form{margin:6px 0 0}
.edyt textarea{min-height:80px}.edyt .siatka{margin-bottom:6px}
.wroc{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;width:92px;height:92px;border-radius:50%;
background:#fff;border:3px solid #111;text-decoration:none;line-height:1;text-align:center;box-shadow:0 3px 8px rgba(0,0,0,.3);flex:none}
.wroc{font-size:40px}.wroc:hover{background:#f0e9d8}
.brazowa{border-left:8px solid #7b4a2a!important;background:#f3e8dd!important}
.fiolet-btn{background:#7d3cff;color:#fff;border:0;border-radius:10px;padding:14px 22px;font-size:17px;font-weight:800;cursor:pointer;box-shadow:0 3px 8px rgba(80,30,160,.35)}
.pilna-btn{background:#d35400;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-size:15px;font-weight:800;cursor:pointer}.pilna-btn:hover{background:#b94700}
.pilne{border:2px solid #d35400;border-radius:12px;padding:10px 12px;margin-top:14px;background:#fff8f2}.pilne h3{margin:0 0 8px;font-size:15px;color:#b94700}.pilne ul{list-style:none;margin:0;padding:0}
.pilne li{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-top:1px solid #f0d9c8}.pilne li:first-child{border-top:0}.pilne a{font-weight:700;color:var(--tekst);text-decoration:none}.pilne a:hover{text-decoration:underline}
.pilne form{margin:0}.pilne .x{background:none;border:0;cursor:pointer;color:#999;font-size:16px;padding:2px 6px}.pilne .x:hover{color:#c0392b}
.fiolet-btn:hover{background:#6a28e8}.fiolet-btn[disabled]{background:#b9a3e6;cursor:not-allowed;box-shadow:none}
.fioletowa{border-left:8px solid #7d3cff!important;background:#efe6ff!important}
.rozowa{border-left:8px solid #e0679a!important;background:#fdeaf2!important}
.czerwona{border-left:8px solid #c0392b!important;background:#fdecea!important}
.dolne{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 18px}
.dolne .grupa{border:1px solid var(--linia);border-radius:10px;padding:10px 12px;background:#fff}
.dolne .grupa h3{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--slaby)}
.dolne .wiersz-g{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.dolne .wiersz-g+.wiersz-g{margin-top:8px}
.dolne form{margin:0;display:flex;gap:8px;align-items:center}.dolne .wiersz-g form:last-child{flex:1}
.dolne select{padding:8px;border:1px solid var(--linia);border-radius:8px;font:inherit;flex:1;min-width:0}
.dolne button{white-space:nowrap}
.dolne .proj{background:#14532d;border-color:#14532d;color:#fff;font-weight:700}
.dolne .inic{background:#86d99a;border-color:#5fbf78;color:#10361d;font-weight:700}
.dolne .grupa.kasowanie{grid-column:1/-1;border-color:#e3b3b3;background:#fff6f6;display:flex;justify-content:space-between;align-items:center}
.dolne .przej{background:#7b4a2a;border-color:#7b4a2a;color:#fff;font-weight:700}
.dolne .kasuj{background:#a32020;border-color:#a32020;color:#fff;font-weight:700}
@media(max-width:700px){.dolne{grid-template-columns:1fr}}
.dolne button[disabled]{opacity:.45;cursor:not-allowed}
.os{display:flex;flex-direction:column;gap:6px;margin:6px 0 18px}
.dzien{text-align:center;margin:8px 0 2px;border-top:1px solid var(--linia);line-height:0}.dzien span{background:#fff;padding:0 10px;font-size:12px;color:var(--slaby);font-weight:700;position:relative;top:-1px}
.bania.mail{background:#d8f5f0;border:2px solid #0f9d8f}
.bania.tel{background:#f1e4ff;border:2px solid #8e44ad}.bania.zd{background:#fff3d6;border-color:#e0b050}
.rzad.srodek{justify-content:center}.rzad.srodek .bania{max-width:88%;width:88%}
.rzad{display:flex}.rzad.ja{justify-content:flex-end}.rzad.on{justify-content:flex-start}
.bania{max-width:78%;border-radius:12px;padding:9px 13px;border:1px solid var(--linia)}
.bania.ja{background:#e3efff;border-color:#b6d1f5;border-bottom-right-radius:3px}.bania.on{background:#eaf5ee;border-color:#b9dcc8;border-bottom-left-radius:3px}
.bania-gora{display:flex;justify-content:space-between;gap:14px;font-size:12px;color:var(--slaby);margin-bottom:4px}.bania-gora b{color:var(--tekst)}
.akta{border:1px solid var(--tekst);border-radius:10px;padding:16px 18px;margin:0 0 18px;background:#fffdf7;box-shadow:0 2px 6px rgba(0,0,0,.08)}
.akta-gora{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;border-bottom:2px solid var(--tekst);padding-bottom:10px;margin-bottom:12px}
.akta-nazwa{font-size:24px;font-weight:800;line-height:1.15}.akta-ocena{text-align:right}.akta-ocena b{display:block;font-size:24px}
.akta-siatka{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px 18px}
.akt-pole span{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--slaby)}.akt-pole b{font-size:15px;word-break:break-word}
.brak{color:#999;font-weight:400;font-style:italic}
.akta-char{margin-top:14px;padding:10px 12px;background:#f4f1e6;border-left:4px solid var(--tekst);border-radius:4px}
.akta-char .pl{margin-bottom:4px}.wej{width:100%;padding:8px;border:1px solid var(--linia);border-radius:8px;font:inherit}
.osoby{display:flex;flex-wrap:wrap;gap:8px}.osoby.lista{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}.osoba{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:8px 14px;border:1px solid var(--tekst);border-radius:8px;text-decoration:none;color:var(--tekst);font-weight:600;background:#fff}.osoba:hover{background:#f3f3f3}.osoba .zaang{display:inline-flex;align-items:center;gap:8px;font-weight:700;white-space:nowrap}
details.mail{border:1px solid var(--linia);border-radius:8px;padding:8px 12px;margin:0 0 6px}details.mail summary{cursor:pointer}
a.lead{text-decoration:none;color:inherit;cursor:pointer}a.lead:hover{background:#fafafa}
.msg{border:1px solid var(--linia);border-radius:10px;padding:10px 14px;margin:0 0 8px;max-width:92%}
.msg.info{background:#fff8e1;border-color:#ecd9a0}.msg.nasza{background:var(--pole)}.msg.jej{background:#eaf5ee;border-color:#b9dcc8;margin-left:8%}
.dl{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;margin:0}.dl dt{color:var(--slaby)}.dl dd{margin:0}.ok{color:var(--ok)}
@media(max-width:900px){.uklad{grid-template-columns:1fr}aside{position:static;max-width:340px;margin:0 auto;order:-1}.kafle{grid-template-columns:1fr 1fr}.siatka,.lead{grid-template-columns:1fr}.lead .poz{text-align:left}}
"""


def _pasek(n: int) -> str:
    n = max(0, min(6, int(n or 0)))
    return '<span class="pasek">' + "".join(f'<i class="{"w" if i < n else ""}"></i>' for i in range(6)) + "</span>"


RODZAJE = {"odezwie_sie": "odezwie się", "zapamieta_kontakt": "zapamięta kontakt", "zainteresowany": "zainteresowany",
           "prosi_o_kontakt": "prosi o kontakt", "przekazal_kontakt": "przekazał kontakt", "odmowa": "odmowa",
           "automat": "automat", "brak_listu": "brak naszego listu", "inne": "inne"}


ZNACZNIK = {"zielona": "🟩 ", "rozowa": "🌸 ", "czerwona": "🟥 ", "szara": "🔍 ", "brazowa": "📖 ", "fioletowa": "🟣 "}


def _kolor(t: dict) -> str:
    """Kolejnosc: fioletowa (wysoka inicjatywa) > brazowa (przejrzana) > szara (u detektywa) > projekt/inicjatywa > zielona. Nowa wiadomosc zdejmuje „przejrzana”."""
    if t.get("wysoka"):
        return "fioletowa"                                      # wysoka inicjatywa: pilny telefon — przebija wszystko
    if t.get("przejrzana"):
        return "brazowa"
    if t.get("u_detektywa"):
        return "szara"
    return t.get("kolor") or ""


def _teczka(t: dict) -> str:
    if t["do_oceny"]:
        stan = '<span class="male">czeka na ocenę</span>' + (f' <span class="zle">{e(t["blad"])}</span>' if t["blad"] else "")
    else:
        stan = (f'<span class="et {"wysoki" if t["pozytywna"] else ""}">{"pozytywna" if t["pozytywna"] else "bez zainteresowania"}</span>'
                f'<span class="et">{e(RODZAJE.get(t["rodzaj"], t["rodzaj"]))}</span>'
                + (f'<span class="et wysoki">termin: {e(t["termin"])}</span>' if t["termin"] else ""))
    kol = _kolor(t)
    return (f'<a class="lead{" " + kol if kol else ""}" href="/teczka/{t["id"]}"><div><b>{e(t["nazwa"])}</b> <span class="male">{e(t["naglowek"])}</span>'
            f'<div>{stan}</div>'
            + (f'<div style="margin-top:4px">{e(t["streszczenie"])}</div>' if t["streszczenie"] else "")
            + (f'<div class="male" style="margin-top:4px">Następny krok: {e(t["nastepny_krok"])}</div>' if t["nastepny_krok"] else "")
            + f'<div class="male">w teczce: {t["od_leada"]} od niej/niego · {t["od_nas"]} od nas · ostatnia {e(t["ostatnia_wiadomosc"])}</div></div>'
            f'<div class="poz">{_pasek(t["ocena"])}<b>{int(t["ocena"])}/6</b><span class="male">ciepłość</span></div></a>')


IKONA_WROC = '<a class="img-btn" href="/" title="Wróć do listy teczek" aria-label="Wróć do archiwum teczek"><img src="/btn-wroc.png?v=3" alt="Wróć do archiwum"></a>'


def _ramka(tresc: str, boczny: str = "") -> str:
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><link rel="icon" type="image/png" href="/ikona.png"><title>{TYTUL}</title><style>{CSS}</style></head>
<body><div class="wrap"><header><h1><img src="/ikona.png" alt=""><a href="/" style="text-decoration:none;color:inherit">{TYTUL}</a></h1>
<div class="pod">Kierownik wysyła odpowiedzi z LinkedIn, Agent (n8n) zakłada teczki i ocenia, kto zareagował pozytywnie na list</div></header>
<div class="uklad"><main>{tresc}</main><aside><img src="/analityczka.png" alt="Analityczka">
<div class="podp">Analityczka zakłada teczki i pilnuje, kto się odezwie</div>{boczny}</aside></div></div></body></html>"""


def _projekt(p: dict) -> str:
    lista = store.poczta_projektu(p["klucz"])
    wiersze = "".join(
        f'<details class="mail"><summary><b>{e(m["temat"] or "(bez tematu)")}</b> <span class="male">{e(m["nadawca"])} · {e(m["kiedy"][:16])}</span></summary>'
        f'<div style="white-space:pre-wrap;margin:6px 0 2px">{e(m["tresc"])}</div></details>' for m in lista)
    return (f'<details class="panel"><summary style="cursor:pointer;font-weight:700">Projekt: {e(p["nazwa"])} ({len(lista)})</summary>'
            + (wiersze or '<div class="male" style="margin-top:6px">Nic nie przypisano. Opisz projekt w prompcie w panelu „Projekty poczty”.</div>')
            + '</details>')


def _panel_projektow(proj: list[dict], licz: dict) -> str:
    opcje = "".join(f'<option value="{e(p["klucz"])}">{"🟥" if p["rodzaj"] == "projekt" else "🌸"} {e(p["nazwa"])} ({licz.get(p["klucz"], 0)})</option>' for p in proj)
    pola = "".join(
        f'<textarea class="projekt-prompt" data-k="{e(p["klucz"])}" name="prompt__{e(p["klucz"])}" '
        f'placeholder="{e(nadzorca.PODPOWIEDZ_PROJEKTU)}"{"" if p is proj[0] else " hidden"}>{e(p["prompt"])}</textarea>' for p in proj)
    if proj:
        glowna = f"""<form method="post" action="/ui/projekty"><label class="pl" for="proj-wybor">Projekt</label>
<select id="proj-wybor">{opcje}</select>
<label class="pl" style="margin-top:10px">Prompt: kiedy wiadomość należy do tego projektu</label>{pola}
<div class="akcje"><button type="submit" class="glowny">Zapisz prompty projektów</button>
<button type="submit" form="usun-projekt" id="usun-btn" style="border-color:#a32020;color:#a32020" onclick="return confirm('Usunąć wybrany projekt? Przypisane maile wrócą do oceny.')">Usuń wybrany projekt</button></div></form>
<form id="usun-projekt" method="post" action="/ui/projekt-usun/{e(proj[0]["klucz"])}"></form>
<script>(function(){{var s=document.getElementById('proj-wybor'),f=document.getElementById('usun-projekt');
function pokaz(){{document.querySelectorAll('.projekt-prompt').forEach(function(t){{t.hidden=t.dataset.k!==s.value}});f.action='/ui/projekt-usun/'+encodeURIComponent(s.value)}}
s.addEventListener('change',pokaz);pokaz()}})()</script>"""
    else:
        glowna = '<div class="male">Nie ma jeszcze żadnego projektu. Dopisz pierwszy poniżej.</div>'
    return f"""<div class="panel" id="projekty"><h2>Projekty i inicjatywy (poczta)</h2>
<div class="male" style="margin-bottom:8px">Wybierz projekt z listy i opisz, jakie osoby, adresy lub firmy do niego należą. Maile pasujące do opisu trafiają do projektu, reszta to śmietnik.</div>
{glowna}
<form method="post" action="/ui/projekt-nowy" class="akcje" style="margin-top:14px;border-top:1px solid var(--linia);padding-top:12px">
<select name="rodzaj" style="padding:8px;border:1px solid var(--linia);border-radius:8px"><option value="projekt">Projekt</option><option value="inicjatywa">Inicjatywa</option></select>
<input type="text" name="nazwa" required placeholder="Nazwa nowego projektu lub inicjatywy" style="flex:1;min-width:220px;padding:8px;border:1px solid var(--linia);border-radius:8px">
<button type="submit">+ Dodaj</button></form></div>"""


def strona(komunikat: str = "") -> str:
    u, k, lista, pr = nadzorca.ustawienia(), store.liczniki(), store.teczki(), store.przebiegi(1)
    pm = store.licznik_poczty()
    modele = ai.modele()
    opcje = "".join(f'<option value="{e(m)}"{" selected" if m == u["model"] else ""}>{e(m)}</option>'
                    for m in (modele if u["model"] in modele else [u["model"]] + modele))
    ostatni = (f'Ostatni przebieg: {e(pr[0]["czas"])} ({e(pr[0]["zrodlo"])}) — nowych teczek {pr[0]["nowych_teczek"]}, '
               f'ocenionych {pr[0]["ocenionych"]}, błędów {pr[0]["bledow"]}. {e(pr[0]["uwaga"])}' if pr else "Agent jeszcze nie pracował.")
    brak = "" if ai.wlaczone() else ' <b class="zle">Brak klucza OpenAI.</b>'
    maja = sorted((t for t in lista if (t["pozytywna"] or t["wymuszona"]) and not t["smietnik"]),
                  key=lambda t: (not t.get("wysoka"), -int(t["ocena"]), t["nazwisko_imie"].lower()))      # fioletowe na górze, potem od najgorętszych (6) do najsłabszych
    osoby = "".join(f'<a class="osoba{" " + _kolor(t) if _kolor(t) else ""}" href="/teczka/{t["id"]}"><span>{ZNACZNIK.get(_kolor(t), "")}{e(t["nazwisko_imie"])} <span class="male">{e(" · ".join(x for x in (t["stanowisko"], t["firma"]) if x))}</span></span>'
                    f'<span class="zaang">{_pasek(t["ocena"])}<b>{int(t["ocena"])}/6</b></span></a>' for t in maja)
    proj = store.projekty()
    kafle_proj = "".join(f'<div class="kafel"><b>{pm["projekty"].get(p["klucz"], 0)}</b><span>{e(p["nazwa"])}</span></div>' for p in proj)
    tresc = f"""{f'<div class="panel"><b>{e(komunikat)}</b></div>' if komunikat else ''}
{panel_odprawy()}
{karta_branz()}
{panel_leadow()}
<div class="kafle"><div class="kafel"><b>{len(maja)}</b><span>teczek</span></div>{kafle_proj}<div class="kafel"><b>{k["smietnik_osoby"] + pm["smietnik"]}</b><span>śmietnik (pomijamy)</span></div></div>
<h2>Teczki ({len(maja)})</h2>
<div class="osoby lista">{osoby or '<span class="male">Żadna osoba nie spełnia jeszcze promptu „kiedy zakładamy teczkę”.</span>'}</div>
<div class="male" style="margin-top:6px">{k["do_oceny"]} teczek czeka na ocenę. Posortowane od najgorętszych (6/6) do najsłabszych. Kliknij nazwisko, żeby wejść do teczki.</div>
<form method="post" action="/ui/ustawienia" class="panel"><h2>Prompty analityczki</h2>
<div class="siatka"><div><label class="pl" for="si">Silnik</label><select id="si" name="silnik"><option value="api"{" selected" if ai.silnik() == "api" else ""}>API OpenAI (klucz, płatne za zapytanie)</option><option value="sdk"{" selected" if ai.silnik() == "sdk" else ""}>SDK — abonament ChatGPT (przez Codex)</option></select>{"" if ai.sdk_gotowy() else '<div class="male zle">Brak CODEX_BRIDGE_URL / TOKEN w .env — SDK nie ruszy.</div>'}</div><div><label class="pl" for="m">Model (tylko dla API)</label><select id="m" name="model">{opcje}</select></div>
<div><label class="pl" for="p">Ile teczek ocenić na jeden przebieg</label><input id="p" type="number" name="porcja" min="1" max="50" value="{u["porcja"]}"></div></div>
<label class="pl" for="pr" style="margin-top:12px">Prompt: kiedy zakładamy teczkę</label><textarea id="pr" name="prompt">{e(u["prompt"])}</textarea>
<label class="pl" for="pd" style="margin-top:12px">Prompt: standardowe zlecenie dla detektywa (używane w „Wyślij do detektywa” w każdej teczce; można użyć {{nazwisko}}, {{firma}}, {{stanowisko}}, {{miasto}}, {{linkedin}})</label>
<textarea id="pd" name="prompt_detektyw">{e(u["prompt_detektyw"])}</textarea>
<div class="akcje"><button type="submit" class="glowny" name="analizuj" value="1"{"" if ai.wlaczone() else " disabled"}>Zapisz i przelicz teraz</button>
<button type="submit">Tylko zapisz</button><span class="male">{ostatni}{brak}</span></div></form>
{_panel_projektow(proj, pm["projekty"])}
<form method="post" action="/ui/import" enctype="multipart/form-data" class="panel"><h2>Wczytaj odpowiedzi z LinkedIn</h2>
<div class="male" style="margin-bottom:8px">Plik <b>messages.csv</b> z archiwum LinkedIn (Ustawienia → Prywatność → Pobierz kopię danych → Wiadomości). Analityk dopisze do istniejących teczek całą rozmowę w obie strony: co wysłałeś i co dostałeś.</div>
<div class="akcje"><input type="file" name="plik" accept=".csv" required><button type="submit" class="glowny">Wczytaj i uzupełnij teczki</button></div>
<label class="male" style="display:block;margin-top:8px"><input type="checkbox" name="nowe" value="1"> założ też NOWE teczki dla osób z pliku, które odpisały (domyślnie tylko uzupełniam istniejące teczki pełnymi rozmowami)</label></form>
<form method="post" action="/ui/zlec-rozmowy" class="panel" style="border-top-color:#c0392b"><h2>Brakujące rozmowy ({len(store.bez_rozmowy())} teczek bez treści)</h2>
<div class="male" style="margin-bottom:8px">Kierownik wyśle agenta GPT, żeby wszedł w LinkedIn i przepisał pełne rozmowy (co wysłałeś, co dostałeś). Dzieje się to też automatycznie z każdym przebiegiem Agenta — agent robi to przy najbliższej wizycie („IDŹ DO KIEROWNIKA”).</div>
<div class="akcje"><button type="submit" class="glowny">Poproś Kierownika o rozmowy</button></div></form>
<form method="post" action="/ui/teczka-url" class="panel" style="border-top-color:#c0392b"><h2>Wklej adresy LinkedIn — teczki same się założą</h2>
<div class="male" style="margin-bottom:8px">Po jednym adresie w linii. Analityk zapyta Kierownika o wszystko, co o osobie wie (kontakt, firma, wysłane listy, powiadomienia, maile).</div>
<textarea name="adresy" required placeholder="https://www.linkedin.com/in/…" style="min-height:90px"></textarea>
<div class="akcje"><button type="submit" class="glowny">Załóż teczki</button></div></form>
<details class="panel"><summary style="cursor:pointer;font-weight:700">+ Dodaj teczkę ręcznie (wklej rozmowę)</summary>
<form method="post" action="/ui/teczka-nowa" style="margin-top:10px"><div class="siatka">
<div><label class="pl">Imię i nazwisko</label><input type="text" name="name" required style="width:100%;padding:8px;border:1px solid var(--linia);border-radius:8px"></div>
<div><label class="pl">Adres profilu LinkedIn</label><input type="text" name="profile_url" style="width:100%;padding:8px;border:1px solid var(--linia);border-radius:8px"></div>
<div><label class="pl">Firma</label><input type="text" name="firma" style="width:100%;padding:8px;border:1px solid var(--linia);border-radius:8px"></div>
<div><label class="pl">Stanowisko</label><input type="text" name="stanowisko" style="width:100%;padding:8px;border:1px solid var(--linia);border-radius:8px"></div></div>
<label class="pl" style="margin-top:10px">Co napisał(a) do mnie (wklej)</label><textarea name="od_niego" placeholder="np. długi opis jego problemów"></textarea>
<label class="pl" style="margin-top:10px">Co ja wysłałem (wklej)</label><textarea name="ode_mnie" placeholder="np. opis mojej oferty"></textarea>
<div class="akcje"><button type="submit" class="glowny">Załóż teczkę</button></div></form></details>
{"".join(_projekt(p) for p in proj)}
<div class="male" style="margin-top:18px">Reszta to śmietnik — Analityk się tym nie zajmuje.</div>"""
    return _ramka(tresc, _panel_pilnych())


def _panel_pilnych() -> str:
    lista = store.lista_pilna()
    if not lista:
        return '<div class="pilne"><h3>📞 Lista pilnego kontaktu</h3><span class="male">Pusta. W teczce kliknij „Wrzuć na listę pilnego obdzwonienia”.</span></div>'
    wiersze = "".join(
        f'<li><span><a href="/teczka/{p["id"]}">{e(store.nazwisko_imie(p["nazwa"]))}</a>'
        f'<div class="male">{e(" · ".join(x for x in (p["stanowisko"], p["firma"]) if x))}'
        + (f'<div><a href="tel:{e(p["telefon"].replace(" ", ""))}">{e(p["telefon"])}</a></div>' if p["telefon"] else "")
        + '</div></span>'
        f'<form method="post" action="/ui/teczka/{p["id"]}/pilna"><input type="hidden" name="wartosc" value="0"><input type="hidden" name="wroc" value="lista">'
        '<button type="submit" class="x" title="Zdejmij z listy (załatwione)">✕</button></form></li>' for p in lista)
    return f'<div class="pilne"><h3>📞 Lista pilnego kontaktu ({len(lista)})</h3><ul>{wiersze}</ul></div>'


def _ikony_boczne(t: dict) -> str:
    return ('<div class="ikony-bok">' + IKONA_WROC
            + f'<form method="post" action="/ui/teczka/{t["id"]}/kasuj" onsubmit="return confirm(\'Skasować teczkę {e(t["nazwa"])} razem z całą zawartością?\')">'
            '<button type="submit" class="ikona-btn" title="Skasuj teczkę" aria-label="Skasuj teczkę"><img src="/ikona-kosz.png?v=3" alt="Skasuj teczkę"></button></form></div>')


def _dolne_przyciski(t: dict) -> str:
    proj = store.projekty()
    ma = {p["klucz"]: p for p in proj}.get(t.get("projekt_klucz") or "")
    domysl = e(t.get("firma") or t["nazwa"]).replace("'", "")

    def zaloz(rodzaj, tekst, kl):
        return (f'<form method="post" action="/ui/teczka/{t["id"]}/zaloz" onsubmit="var n=prompt(\'Nazwa {"projektu" if rodzaj == "projekt" else "inicjatywy"}:\',\'{domysl}\');'
                f'if(!n)return false;this.nazwa.value=n;return true">'
                f'<input type="hidden" name="rodzaj" value="{rodzaj}"><input type="hidden" name="nazwa" value="">'
                + f'<button type="submit" class="img-btn" title="{tekst}"><img src="/btn-{"zaloz" if rodzaj == "projekt" else "zaloz-inic"}.png?v=3" alt="{tekst}"></button></form>')

    def przypisz(rodzaj, tekst, kl):
        lista = [p for p in proj if p["rodzaj"] == rodzaj]
        opcje = "".join(f'<option value="{e(p["klucz"])}"{" selected" if ma and ma["klucz"] == p["klucz"] else ""}>{e(p["nazwa"])}</option>' for p in lista)
        return (f'<form method="post" action="/ui/teczka/{t["id"]}/przypisz"><select name="klucz">'
                f'{opcje or "<option value=>(brak — najpierw załóż)</option>"}</select>'
                + f'<button type="submit" class="img-btn"{"" if lista else " disabled"} title="{tekst}"><img src="/btn-{"przypisz" if rodzaj == "projekt" else "przypisz-inic"}.png?v=3" alt="{tekst}"></button></form>')

    def grupa(naglowek, rodzaj, kl, zal, prz):
        return (f'<div class="grupa"><h3>{naglowek}</h3><div class="wiersz-g">{zaloz(rodzaj, zal, kl)}</div>'
                f'<div class="wiersz-g">{przypisz(rodzaj, prz, kl)}</div></div>')

    prz = bool(t.get("przejrzana"))
    przejrzana = (f'<form method="post" action="/ui/teczka/{t["id"]}/przejrzana"><input type="hidden" name="wartosc" value="{0 if prz else 1}">'
                  f'<button type="submit" class="przej">{"✓ Przejrzana — cofnij" if prz else "Oznacz jako przejrzaną"}</button></form>'
                  f'<span class="male">{"Teczka jest brązowa." if prz else "Teczka zrobi się brązowa."} Nowa wiadomość od osoby zdejmie ten stan.</span>')
    pil = bool(t.get("pilna"))
    pilna = (f'<form method="post" action="/ui/teczka/{t["id"]}/pilna"><input type="hidden" name="wartosc" value="{0 if pil else 1}">'
             f'<button type="submit" class="pilna-btn">{"📞 Na liście pilnych — zdejmij" if pil else "📞 Wrzuć na listę pilnego obdzwonienia"}</button></form>'
             f'<span class="male">{"Teczka jest na liście pilnego kontaktu (prawa kolumna archiwum)." if pil else "Trafi na szybką listę do obdzwonienia / kontaktu w archiwum."}</span>')
    wys = bool(t.get("wysoka"))
    w_inic = t.get("kolor") == "rozowa"                 # fioletowa tylko dla teczki z przypisana inicjatywa
    if w_inic or wys:
        wysoka = (f'<form method="post" action="/ui/teczka/{t["id"]}/wysoka"><input type="hidden" name="wartosc" value="{0 if wys else 1}">'
                  f'<button type="submit" class="fiolet-btn">{"🟣 Wysoka inicjatywa — zdejmij" if wys else "🟣 Wysoka inicjatywa (pilny telefon)"}</button></form>'
                  f'<span class="male">{"Teczka jest fioletowa — do pilnego oddzwonienia." if wys else "Teczka zrobi się fioletowa: osoba z dużą szansą na pilne oddzwonienie."}</span>')
    else:
        wysoka = ('<button type="button" class="fiolet-btn" disabled>🟣 Wysoka inicjatywa (pilny telefon)</button>'
                  '<span class="male">Dostępne dopiero, gdy teczka ma założoną inicjatywę — najpierw przypisz ją do inicjatywy.</span>')
    stan = ""
    if ma:
        stan = (f'<form method="post" action="/ui/teczka/{t["id"]}/przypisz"><span class="male">Teczka jest w: <b>{e(ma["nazwa"])}</b> '
                f'({"projekt" if ma["rodzaj"] == "projekt" else "inicjatywa"})</span><input type="hidden" name="klucz" value="">'
                f'<button type="submit">Wypisz</button></form>')
    return ('<div class="dolne">'
            + grupa("Projekt", "projekt", "proj", "Załóż projekt", "Przypisz do projektu")
            + grupa("Inicjatywa", "inicjatywa", "inic", "Załóż inicjatywę", "Przypisz do inicjatywy")
            + '<div class="grupa przejrzana-g"><h3>Stan teczki</h3><div class="wiersz-g">' + przejrzana + '</div><div class="wiersz-g" style="margin-top:10px">' + pilna + '</div></div>'
            + '<div style="display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center"><div class="grupa fiolet-g" style="width:100%"><h3>Wysoka inicjatywa</h3><div class="wiersz-g" style="flex-direction:column;align-items:flex-start">' + wysoka + '</div></div><a class="img-btn" href="/" title="Wróć do listy teczek" aria-label="Wróć do archiwum teczek"><img src="/btn-wroc.png?v=3" alt="Wróć do archiwum"></a></div>'
            + '<div class="grupa kasowanie"><div>' + (stan or '<span class="male">Kasowanie usuwa teczkę razem z całą zawartością.</span>') + '</div>'
            f'<form method="post" action="/ui/teczka/{t["id"]}/kasuj" onsubmit="return confirm(\'Skasować teczkę {e(t["nazwa"])} razem z całą zawartością?\')">'
            '<button type="submit" class="ikona-btn" title="Skasuj teczkę" aria-label="Skasuj teczkę"><img src="/ikona-kosz.png?v=3" alt="Skasuj teczkę"></button></form></div></div>')


def strona_teczki(t: dict) -> str:
    def edytor(m) -> str:
        aktualny = f'{m["kierunek"]}|{m["rodzaj"]}'
        typy = [("zdarzenie|rozmowa telefoniczna", "📞 Rozmowa telefoniczna"), ("zdarzenie|spotkanie", "📅 Spotkanie"),
                ("od_leada|wiadomość LinkedIn", "Napisał(a) do mnie w LinkedIn"), ("od_nas|wiadomość LinkedIn", "Ja napisałem w LinkedIn"),
                ("od_leada|e-mail", "E-mail od niej/niego"), ("od_nas|e-mail", "E-mail ode mnie"), ("zdarzenie|notatka", "📝 Notatka")]
        if aktualny not in dict(typy):
            typy.append((aktualny, f'{m["rodzaj"] or "wpis"} (obecny)'))
        opcje = "".join(f'<option value="{e(v)}"{" selected" if v == aktualny else ""}>{e(n)}</option>' for v, n in typy)
        ts = m["ts"] or ""
        return (f'<details class="edyt"><summary>✎ edytuj / usuń wpis</summary>'
                f'<form method="post" action="/ui/wiadomosc/{m["id"]}/edytuj"><div class="siatka"><div><label class="pl">Co to jest</label><select name="typ">{opcje}</select></div>'
                f'<div><label class="pl">Kiedy (data i godzina)</label><div style="display:flex;gap:8px"><input type="date" name="data" value="{e(ts[:10])}" class="wej">'
                f'<input type="time" name="godzina" value="{e(ts[11:16])}" class="wej"></div></div></div>'
                f'<textarea name="tekst" required>{e(m["tekst"])}</textarea>'
                f'<div class="akcje"><button type="submit" class="glowny">Zapisz poprawkę</button></div></form>'
                f'<form method="post" action="/ui/wiadomosc/{m["id"]}/usun" onsubmit="return confirm(\'Usunąć ten wpis z teczki?\')">'
                f'<button type="submit" style="border-color:#a32020;color:#a32020">Usuń wpis</button></form></details>')

    def bańka(m, nr):
        tel = "telefon" in (m["rodzaj"] or "")
        mail = (m["rodzaj"] or "") == "e-mail"
        if m["kierunek"] == "zdarzenie":                        # rozmowa telefoniczna, spotkanie, notatka: karta na środku
            kolor = "tel" if tel else "zd"
            ikona = "📞 " if tel else ("📅 " if "spotkanie" in (m["rodzaj"] or "") else "📝 ")
            return (f'<div class="rzad srodek"><div class="bania {kolor}"><div class="bania-gora"><b>{ikona}{e(m["rodzaj"].capitalize())}</b>'
                    f'<span>#{nr} · {e(m["ts"] or m["kiedy"] or "data nieznana")}</span></div>'
                    f'<div style="white-space:pre-wrap">{e(m["tekst"])}</div>{edytor(m)}</div></div>')
        nasza = m["kierunek"] == "od_nas"
        czas = m["ts"] or m["kiedy"] or "data nieznana"
        autor = "Ja" if nasza else t["nazwa"]
        rodzaj = {"list": "list", "zaproszenie": "zaproszenie", "nasza odpowiedź": "moja odpowiedź", "powiadomienie": "powiadomienie LinkedIn",
                  "wklejone": "wklejone", "odpowiedz": "odpowiedź", "e-mail": "e-mail"}.get(m["rodzaj"], m["rodzaj"])
        return (f'<div class="rzad {"ja" if nasza else "on"}"><div class="bania {"tel" if tel else ("mail" if mail else ("ja" if nasza else "on"))}">'
                f'<div class="bania-gora"><b>{"✉️ " if mail else ""}{e(autor)}</b><span>#{nr} · {e(czas)} · {e(rodzaj)}</span></div>'
                f'<div style="white-space:pre-wrap">{e(m["tekst"])}</div>{edytor(m)}</div></div>')

    korespondencja = [m for m in t["wiadomosci"] if m["kierunek"] in ("od_nas", "od_leada", "zdarzenie")]
    calosc = [m for m in t["wiadomosci"] if m["kierunek"] == "rozmowa"]
    info = [m for m in t["wiadomosci"] if m["kierunek"] == "info"]
    os_czasu, ostatni_dzien = [], None
    for i, m in enumerate(korespondencja, 1):
        dzien = (m["ts"] or "")[:10]
        if dzien and dzien != ostatni_dzien:
            os_czasu.append(f'<div class="dzien"><span>{e(dzien)}</span></div>')
            ostatni_dzien = dzien
        elif not dzien and ostatni_dzien != "?":
            os_czasu.append('<div class="dzien"><span>data nieznana</span></div>')
            ostatni_dzien = "?"
        os_czasu.append(bańka(m, i))
    wiad = (
        (f'<h3>Pełny zapis rozmowy z LinkedIn</h3>' + "".join(
            f'<div class="msg info"><div class="male">przepisano {e(m["kiedy"])}</div><div style="white-space:pre-wrap">{e(m["tekst"])}</div></div>' for m in calosc)
         if calosc else "")
        + (f'<div class="os">{"".join(os_czasu)}</div>' if os_czasu else '<div class="male">Brak wiadomości w teczce.</div>')
        + (f'<h3>Informacje z Kierownika</h3>' + "".join(
            f'<div class="msg info"><div class="male">{e(m["kiedy"])}</div>{e(m["tekst"])}</div>' for m in info) if info else ""))
    ocena = ("" if t["do_oceny"] else
             f'<div class="panel"><h2>Ocena analityczki</h2><dl class="dl"><dt>Odpowiedź</dt><dd>{"pozytywna" if t["pozytywna"] else "bez zainteresowania"}'
             f' · {e(RODZAJE.get(t["rodzaj"], t["rodzaj"]))}</dd>'
             + (f'<dt>Termin kontaktu</dt><dd>{e(t["termin"])}</dd>' if t["termin"] else "")
             + f'<dt>Streszczenie</dt><dd>{e(t["streszczenie"])}</dd><dt>Następny krok</dt><dd>{e(t["nastepny_krok"])}</dd>'
             f'<dt>Ciepłość</dt><dd>{_pasek(t["ocena"])} {int(t["ocena"])}/6</dd></dl>'
             f'<div class="male">model {e(t["model"])} · {e(t["ocenione"])}</div></div>')
    link = (f' · <a href="{e(t["profil_url"])}" target="_blank" rel="noopener">profil LinkedIn</a>' if t["profil_url"] else "") + \
           (f' · <a href="{e(t["watek_url"])}" target="_blank" rel="noopener">otwórz rozmowę w LinkedIn</a>' if t["watek_url"] else "")
    dane = " · ".join(x for x in (t["stanowisko"], t["firma"]) if x)
    opcje_oceny = "".join(f'<option value="{i}"{" selected" if int(t["ocena"]) == i and t.get("ocena_reczna") is not None else ""}>{i}/6</option>' for i in range(7))
    zlec = store.zlecenia_teczki(t["id"])
    historia_zlec = "".join(
        f'<div class="male">📤 {e(zl["utworzono"])}{" · 📞 tylko telefon" if zl.get("tryb") == "telefon" else ""} — {"wykonane: " + e(zl["wynik"][:200]) if zl["status"] == "wykonane" else "czeka na detektywa"}</div>'
        for zl in zlec)
    detektyw = (f'<form method="post" action="/ui/teczka/{t["id"]}/detektyw" class="panel" style="border-top-color:#6c3483"><h2>🕵️ Wyślij do detektywa</h2>'
                f'<div class="male" style="margin-bottom:6px">Gdy osoba wyraziła chęć, ale nie dała żadnego namiaru — detektyw ma znaleźć adres, telefon i miejsce, gdzie można ją spotkać. Prompt możesz zmienić przed wysłaniem.</div>'
                f'<textarea name="prompt" required style="min-height:150px">{e(nadzorca.prompt_detektywa(t))}</textarea>'
                f'<div class="akcje"><button type="submit" class="img-btn" title="Wyślij do detektywa"><img src="/btn-wyslij.png?v=3" alt="Wyślij do detektywa"></button>'
                f'<button type="submit" formaction="/ui/teczka/{t["id"]}/detektyw-telefon" formnovalidate class="img-btn" '
                f'title="Detektyw szuka wyłącznie numeru telefonu tej osoby i niczego więcej"><img src="/btn-telefon.png?v=3" alt="Znajdź tylko telefon"></button><span style="margin-left:auto"><a class="img-btn" href="/" title="Wróć do listy teczek" aria-label="Wróć do archiwum teczek"><img src="/btn-wroc.png?v=3" alt="Wróć do archiwum"></a></span></div>{historia_zlec}</form>')
    akcje = (detektyw + f'<form method="post" action="/ui/teczka/{t["id"]}/ocena" class="panel"><h2>Poziom zaangażowania</h2>'
             f'<div class="akcje">{_pasek(t["ocena"])} <b>{int(t["ocena"])}/6</b>'
             f'<select name="ocena" style="width:auto"><option value="">(wg modelu: {int(t.get("ocena_ai") or 0)}/6)</option>{opcje_oceny}</select>'
             f'<button type="submit">Ustaw</button></div></form>'
             f'<form method="post" action="/ui/teczka/{t["id"]}/wiadomosc" class="panel"><h2>Dopisz do teczki</h2>'
             f'<div class="siatka"><div><label class="pl">Co to jest</label><select name="typ">'
             f'<option value="zdarzenie|rozmowa telefoniczna">📞 Rozmowa telefoniczna</option>'
             f'<option value="zdarzenie|spotkanie">📅 Spotkanie</option>'
             f'<option value="od_leada|wiadomość LinkedIn">Napisał(a) do mnie w LinkedIn</option>'
             f'<option value="od_nas|wiadomość LinkedIn">Ja napisałem w LinkedIn</option>'
             f'<option value="od_leada|e-mail">E-mail od niej/niego</option><option value="od_nas|e-mail">E-mail ode mnie</option>'
             f'<option value="zdarzenie|notatka">📝 Notatka</option></select></div>'
             f'<div><label class="pl">Kiedy to się stało (data i godzina)</label><div style="display:flex;gap:8px">'
             f'<input type="date" name="data" value="{datetime.now().strftime("%Y-%m-%d")}" class="wej"><input type="time" name="godzina" class="wej"></div></div></div>'
             f'<label class="pl" style="margin-top:10px">Treść / opis (np. „rozmowa 30 min, wysłałem ofertę usług”)</label><textarea name="tekst" required></textarea>'
             f'<div class="akcje"><button type="submit" class="glowny">Dopisz</button></div></form>'
             + _dolne_przyciski(t))
    def pole(etykieta, wartosc, link="", brak=False):
        w = e(wartosc) if wartosc else ('<span class="zle" style="color:#c0261e;font-weight:700">nie udało się ustalić telefonu</span>' if brak else '<span class="brak">brak danych</span>')
        if wartosc and link:
            w = f'<a href="{e(link)}" target="_blank" rel="noopener">{w}</a>'
        return f'<div class="akt-pole"><span>{etykieta}</span><b>{w}</b></div>'

    www = t.get("www") or ""
    www_link = www if www.startswith("http") else (f"https://{www}" if www else "")
    ostatni = max((m["kiedy"] for m in t["wiadomosci"] if m["kierunek"] in ("od_leada", "rozmowa")), default="")
    kol = _kolor(t)
    odznaka = {"fioletowa": "🟣 WYSOKA INICJATYWA — pilnie oddzwonić", "szara": "🔍 u detektywa — czeka na raport", "brazowa": "📖 przejrzana" + (f' · {"🟥 projekt" if t.get("kolor") == "czerwona" else "🌸 inicjatywa"}' if t.get("kolor") in ("czerwona", "rozowa") else "")
               + (" · 🔍 u detektywa" if t.get("u_detektywa") else ""), "zielona": "🟩 lead od wywiadu — szukamy kontaktu", "rozowa": "🌸 INICJATYWA", "czerwona": "🟥 PROJEKT"}.get(kol, "")
    karta = f"""<div class="akta{" " + kol if kol else ""}">
<div class="akta-gora"><div><div class="akta-nazwa">{e(t["nazwa"])}</div>{f'<div><b>{odznaka}</b></div>' if odznaka else ''}<div class="male">{e(t["stanowisko"] or t["naglowek"] or "stanowisko nieznane")}</div></div>
<div class="akta-ocena">{_pasek(t["ocena"])}<b>{int(t["ocena"])}/6</b><span class="male">zaangażowanie</span>{f'<span class="male" style="display:block;max-width:240px">Wywiadowca: publicznie mówi o AI ({int(t["wywiad_zaang"])}/6) — to nie jest odpowiedź na nas</span>' if t.get("wywiad_zaang") and not t["ocena"] else ""}</div></div>
<div class="akta-siatka">{pole("Firma", t["firma"])}{pole("Miasto", t["miasto"])}{pole("Telefon", t["telefon"], ("tel:" + t["telefon"].replace(" ", "")) if t["telefon"] else "", brak=bool(t.get("telefon_brak")) and not t["telefon"])}
{pole("E-mail", t["email"], ("mailto:" + t["email"]) if t["email"] else "")}{pole("Strona www", www, www_link)}{pole("LinkedIn", "profil" if t["profil_url"] else "", t["profil_url"])}
{pole("Rozmowa w LinkedIn", "otwórz" if t["watek_url"] else "", t["watek_url"])}{pole("Ostatnia wiadomość od niej/niego", ostatni)}</div>
<div class="akta-char"><span class="pl" style="display:block">Charakterystyka</span>{e(t["charakterystyka"]) if t["charakterystyka"] else '<span class="brak">Czeka na ocenę — charakterystykę zapisze analityczka.</span>'}</div>
<details style="margin-top:8px"><summary style="cursor:pointer" class="male">✎ Edytuj dane teczki (wszystkie pola; puste pole = skasuj wartość)</summary>
<form method="post" action="/ui/teczka/{t["id"]}/dane" class="siatka" style="margin-top:8px">
<div><label class="pl">Imię i nazwisko</label><input type="text" name="nazwa" value="{e(t["nazwa"])}" class="wej"></div>
<div><label class="pl">Firma</label><input type="text" name="firma" value="{e(t["firma"])}" class="wej"></div>
<div><label class="pl">Stanowisko</label><input type="text" name="stanowisko" value="{e(t["stanowisko"])}" class="wej"></div>
<div><label class="pl">Miasto</label><input type="text" name="miasto" value="{e(t["miasto"])}" class="wej"></div>
<div><label class="pl">Telefon</label><input type="text" name="telefon" value="{e(t["telefon"])}" class="wej"></div>
<div><label class="pl">E-mail</label><input type="text" name="email" value="{e(t["email"])}" class="wej"></div>
<div><label class="pl">Strona www</label><input type="text" name="www" value="{e(t["www"])}" class="wej"></div>
<div><label class="pl">Profil LinkedIn (adres)</label><input type="text" name="profil_url" value="{e(t["profil_url"])}" class="wej"></div>
<div><label class="pl">Rozmowa w LinkedIn (adres)</label><input type="text" name="watek_url" value="{e(t["watek_url"])}" class="wej"></div>
<div style="grid-column:1/-1"><label class="pl">Charakterystyka (Twoja wersja nie jest nadpisywana przez model)</label><textarea name="charakterystyka" style="min-height:90px">{e(t["charakterystyka"])}</textarea></div>
<div><button type="submit" class="glowny" style="font-size:14px;padding:9px 18px">Zapisz dane</button></div></form></details></div>"""
    return _ramka(f'<p><a href="/">← wszystkie teczki</a></p>{karta}{ocena}'
                  f'<h3>Korespondencja — od najstarszej do najnowszej ({len(t["wiadomosci"])})</h3>{wiad}{akcje}', _ikony_boczne(t))


# --------------------------------------------------------------- odprawa strategiczna

CSS_ODPRAWA = """
.odp-poz{border:1px solid var(--linia);border-left:6px solid var(--ok);border-radius:8px;padding:12px 16px;margin:0 0 10px;background:#fff}
.odp-poz.pilne-p{border-left-color:#d35400;background:#fff8f2}.odp-poz.persp{border-left-color:#7d3cff}.odp-poz.odp{border-left-color:#8a8a8a;background:#f5f5f5}
.odp-poz h3{margin:0 0 4px;font-size:16px}.odp-poz h3 a{color:var(--tekst)}.odp-poz p{margin:4px 0}
.odp-nr{display:inline-block;min-width:26px;text-align:center;background:#d35400;color:#fff;border-radius:50%;margin-right:8px;font-weight:800}
.odp-akcja{display:inline-block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;border:1px solid #d35400;color:#b94700;border-radius:4px;padding:0 6px;margin-left:8px;font-weight:700}
.odp-start{background:#f4f1e6;border-left:4px solid var(--tekst);border-radius:4px;padding:6px 10px;margin:6px 0;font-style:italic}
.odp-naglowek{font-size:17px;line-height:1.5;border:2px solid var(--tekst);border-radius:10px;padding:14px 18px;background:#fffdf7;margin-bottom:18px}
"""


def _osoba_odp(ludzie: dict, i) -> str:
    try:
        t = ludzie.get(store.scalone_id().get(int(i), int(i)))        # teczka scalona z inna: stare id z odprawy wskazuje na docelowa
    except (TypeError, ValueError):
        t = None
    if not t:
        return e(f"(nieznana teczka {i})")
    firma = " · ".join(x for x in (t["stanowisko"], t["firma"]) if x)
    return f'<a href="/teczka/{t["id"]}">{e(t["nazwisko_imie"])}</a>' + (f' <span class="male">{e(firma)}</span>' if firma else "")


def _teraz_odprawy(plan: dict, ludzie: dict) -> str:
    """Na samym poczatku: co jest dzis i jutro (kalendarz, rozmowy, rekrutacje), zalegle telefony, swieze odpowiedzi klientow, pilne i propozycje."""
    out = ""
    zal = plan.get("_zalegle") or []
    if zal:
        out += '<div class="odp-poz pilne-p" style="border-left-color:#a32020"><h3>⏰ Zaległe telefony — w teczce nie ma wpisu, że zadzwoniłeś</h3>' + "".join(
            f'<p>{_osoba_odp(ludzie, z["id"])} <b class="zle">— {z["dni"]} dni zwłoki</b> <span class="male">(zalecone {e(z["od"])})</span></p>' for z in zal) + \
            '<div class="male">Analityczka będzie to przypominać każdego dnia, dopóki nie dopiszesz w teczce rozmowy telefonicznej lub notatki.</div></div>'
    nowe = plan.get("_nowe_od_klientow") or []
    if nowe:
        out += f'<div class="odp-poz pilne-p"><h3>✉️ Napisali do Ciebie — czekają na odpowiedź ({len(nowe)})</h3>' + "".join(
            f'<p>{_osoba_odp(ludzie, n["id"])} <span class="male">{e(n["kiedy"][:16])}</span><br>'
            f'<span class="odp-start" style="display:block">{e(n["tekst"])}</span>'
            + (f'<a href="{e(n["url"])}" target="_blank" rel="noopener">Otwórz w LinkedIn ↗</a>' if n.get("url") else "") + '</p>' for n in nowe) + '</div>'
    dop = plan.get("_dopisane_w_dzien") or []
    if dop:
        out += '<div class="odp-poz pilne-p"><h3>🔔 Dopisane w ciągu dnia — po nocnej odprawie przyszło coś pilnego</h3>' + "".join(
            f'<p>{_osoba_odp(ludzie, d["id"])} <span class="odp-akcja">{e(d.get("akcja", ""))}</span> <span class="male">{e(d.get("kiedy", ""))} · dopisane {e(d.get("czas", ""))}</span><br>{e(d.get("dlaczego", ""))}</p>' for d in dop) + '</div>'
    t = plan.get("_teraz")
    if t:
        def wiersz(m):
            kiedy = (m.get("termin") or m.get("received") or "")[:16]
            link = (f' <a href="{e(m["thread_url"])}" target="_blank" rel="noopener">LinkedIn ↗</a>' if m.get("thread_url") else "")
            return (f'<p><b>{e(kiedy)}</b> {e(m.get("subject", ""))}{link}<br><span class="male">{e(m.get("summary") or m.get("sender") or "")}</span></p>')
        spot = (t.get("meetings") or {}).get("calendar", []) + (t.get("meetings") or {}).get("mail", [])
        blok = [("📅 Spotkania, rozmowy, rekrutacje — dziś i jutro", spot), ("🔥 Pilne w poczcie", t.get("urgent") or []),
                ("💼 Propozycje (rekruterzy, oferty)", t.get("offers") or [])]
        out += '<div class="odp-poz persp"><h3>Teraz w kalendarzu i poczcie</h3>' + "".join(
            f'<div><b>{tyt}</b> <span class="male">({len(r)})</span>{"".join(wiersz(m) for m in r) or "<p class=male>Nic.</p>"}</div>' for tyt, r in blok) + \
            '<div class="male"><a href="https://kierownik.sigmaquality.pl/#crm" target="_blank" rel="noopener">Otwórz CRM w Kierowniku ↗</a></div></div>'
    return out


def strona_odprawy(komunikat: str = "") -> str:
    o = strateg.ostatnia()
    ust = strateg.ustawienia()
    modele = ai.modele()
    opcje = "".join(f'<option value="{e(m)}"{" selected" if m == ust["model"] else ""}>{e(m)}</option>'
                    for m in (modele if ust["model"] in modele else [ust["model"]] + modele))
    ludzie = {t["id"]: t for t in store.teczki()}
    trwa = bool(o and o["status"] == "trwa")
    odswiez = '<meta http-equiv="refresh" content="15">' if trwa else ""
    stan = ""
    if trwa:
        stan = f'<div class="panel"><b>Analityczka pracuje…</b> {e(o["postep"] or "start")}<div class="male">Strona odświeża się sama. Pełne przejście przez wszystkie teczki trwa kilka minut.</div></div>'
    elif o and o["status"] == "blad":
        stan = f'<div class="panel" style="border-top-color:#a32020"><b class="zle">Ostatnia odprawa nie wyszła:</b> {e(o["blad"])}</div>'
    plan = o["plan"] if o else None
    tresc = f"{odswiez}<style>{CSS_ODPRAWA}</style>" + (f'<div class="panel"><b>{e(komunikat)}</b></div>' if komunikat else "") + stan
    tresc += f"""<form method="post" action="/ui/odprawa" class="panel"><h2>Odprawa strategiczna</h2>
<div class="male" style="margin-bottom:8px">Analityczka przeczyta wszystkie aktywne teczki ({len(strateg._aktywne())}), porówna osoby ze sobą i powie, co jest pilne, co perspektywiczne,
kogo połączyć i kogo odpuścić. {f"Ostatni gotowy plan: {e(o['plan_czas'])} ({e(o['plan_model'])})." if plan else "Jeszcze nie było odprawy."}</div>
<div class="akcje"><button type="submit" class="glowny"{" disabled" if trwa or not ai.wlaczone() else ""}>Zrób odprawę teraz</button></div></form>"""
    if plan:
        tresc += _teraz_odprawy(plan, ludzie)
        tresc += f'<div class="odp-naglowek"><div class="male">{e(plan.get("_dzien", ""))}</div>{e(plan.get("naglowek", ""))}</div>'
        tresc += f'<h2>Na jutro ({len(plan.get("na_jutro") or [])})</h2>'
        for n, p in enumerate(plan.get("na_jutro") or [], 1):
            tresc += (f'<div class="odp-poz pilne-p"><h3><span class="odp-nr">{e(p.get("priorytet", n))}</span>{_osoba_odp(ludzie, p.get("id"))}'
                      f'<span class="odp-akcja">{e(p.get("akcja", ""))}</span> <span class="male">{e(p.get("kiedy", ""))}</span></h3>'
                      f'<p>{e(p.get("dlaczego", ""))}</p>'
                      + (f'<div class="odp-start">„{e(p["jak_zaczac"])}”</div>' if p.get("jak_zaczac") else "")
                      + (f'<p class="male">Jeśli nie: {e(p["ryzyko"])}</p>' if p.get("ryzyko") else "") + '</div>')
        if plan.get("w_tym_tygodniu"):
            tresc += f'<h2>W tym tygodniu ({len(plan["w_tym_tygodniu"])})</h2>'
            for p in plan["w_tym_tygodniu"]:
                tresc += (f'<div class="odp-poz"><h3>{_osoba_odp(ludzie, p.get("id"))}<span class="odp-akcja">{e(p.get("akcja", ""))}</span> '
                          f'<span class="male">{e(p.get("kiedy", ""))}</span></h3><p>{e(p.get("dlaczego", ""))}</p>'
                          + (f'<div class="odp-start">„{e(p["jak_zaczac"])}”</div>' if p.get("jak_zaczac") else "") + '</div>')
        if plan.get("perspektywiczne"):
            tresc += f'<h2>Perspektywiczne ({len(plan["perspektywiczne"])})</h2>'
            for p in plan["perspektywiczne"]:
                tresc += (f'<div class="odp-poz persp"><h3>{_osoba_odp(ludzie, p.get("id"))} <span class="male">wrócić: {e(p.get("kiedy_wrocic", ""))}</span></h3>'
                          f'<p>{e(p.get("dlaczego", ""))}</p>'
                          + (f'<p class="male">Podtrzymać: {e(p["co_podtrzymac"])}</p>' if p.get("co_podtrzymac") else "") + '</div>')
        if plan.get("powiazania"):
            tresc += "<h2>Powiązania między klientami</h2>"
            for p in plan["powiazania"]:
                osoby = ", ".join(_osoba_odp(ludzie, i) for i in p.get("ids") or [])
                tresc += (f'<div class="odp-poz persp"><h3>{osoby}</h3><p>{e(p.get("opis", ""))}</p>'
                          + (f'<p><b>Jak wykorzystać:</b> {e(p["jak_wykorzystac"])}</p>' if p.get("jak_wykorzystac") else "") + '</div>')
        if plan.get("uwagi_strategiczne"):
            tresc += f'<div class="panel"><h2>Uwagi strategiczne</h2><p>{e(plan["uwagi_strategiczne"])}</p></div>'
        if plan.get("odpuscic"):
            tresc += f'<details class="panel"><summary style="cursor:pointer;font-weight:700">Do odpuszczenia ({len(plan["odpuscic"])})</summary>'
            tresc += "".join(f'<div class="odp-poz odp"><h3>{_osoba_odp(ludzie, p.get("id"))}</h3><p>{e(p.get("powod", ""))}</p></div>' for p in plan["odpuscic"])
            tresc += "</details>"
        if plan.get("_bez_raportu"):
            tresc += f'<div class="male">Model nie ocenił {len(plan["_bez_raportu"])} teczek — uruchom odprawę jeszcze raz.</div>'
    tresc += f"""<form method="post" action="/ui/odprawa/ustawienia" class="panel"><h2>Ustawienia odprawy</h2>
<label class="pl" for="si2">Silnik (wspólny dla całego Analityka)</label><select id="si2" name="silnik"><option value="api"{" selected" if ai.silnik() == "api" else ""}>API OpenAI (klucz, płatne za zapytanie)</option><option value="sdk"{" selected" if ai.silnik() == "sdk" else ""}>SDK — abonament ChatGPT (przez Codex)</option></select>
<label class="pl" for="mo" style="margin-top:12px">Model odprawy w SDK (abonament) — ocena teczek zostaje na modelu z ustawień SDK (Luna)</label>
<select id="mo" name="model_sdk_odprawa">{"".join(f'<option value="{e(m)}"{" selected" if m == ust["model_sdk"] else ""}>{e(m)}</option>' for m in ai.SDK_MODELE)}</select>
<label class="pl" for="ms" style="margin-top:12px">Model do myślenia strategicznego (tylko dla API)</label><select id="ms" name="model">{opcje}</select>
<label class="pl" for="ks" style="margin-top:12px">Kontekst: kim jesteś, co sprzedajesz, jakie masz priorytety (Analityczka bierze to pod uwagę przy ocenie)</label>
<textarea id="ks" name="kontekst">{e(ust["kontekst"])}</textarea>
<div class="akcje"><button type="submit">Zapisz</button></div></form>"""
    return _ramka(tresc, _panel_pilnych())


def panel_odprawy() -> str:
    """Wejscie do odprawy na stronie glownej: skrot ostatniego planu."""
    o = strateg.ostatnia()
    if o and o["status"] == "trwa":
        info = f'Trwa… {e(o["postep"])}'
    elif o and o["plan"]:
        info = f'Ostatni plan: {e(o["plan_czas"])}. ' + e((o["plan"].get("naglowek") or "")[:260])
    else:
        info = "Jeszcze nie było odprawy."
    return (f'<div class="panel" style="border-top-color:#d35400"><h2>🧭 Co jest najważniejsze?</h2><div class="male" style="margin-bottom:8px">{info}</div>'
            '<div class="akcje"><a href="/odprawa" style="font-weight:700">Otwórz odprawę strategiczną →</a></div></div>')


def panel_zaleglych() -> str:
    """Zaległe leady: kto przyjął zaproszenie, a listu nie dostał — dzienna lista dla Kierownika."""
    import zalegle
    z = zalegle.ostatnie()
    if z:
        info = (f'Lista z {e(z.get("czas", ""))}: do Kierownika poszło <b>{len(z.get("wybrane", []))}</b> osób. '
                f'Wszystkich luk (zaproszenie bez listu, {zalegle.MIN_DNI}–{zalegle.MAX_DNI} dni): <b>{z.get("luk", 0)}</b>; '
                f'czeka, aż przyjmie zaproszenie: {z.get("czeka_na_przyjecie", 0)}.')
        lista = "".join(f'<li><a href="{e(l["profile_url"])}" target="_blank">{e(l["name"] or l["profile_url"])}</a> '
                        f'<span class="male">{e(" · ".join(x for x in (l.get("headline") or l.get("company"), l.get("powod")) if x))}</span></li>'
                        for l in z.get("wybrane", []))
    else:
        info, lista = "Lista jeszcze nie powstała — Agent zrobi ją przy pierwszym przebiegu po 5:00.", ""
    return (f'<form method="post" action="/ui/zalegle" class="panel" style="border-top-color:#14532d"><h2>📬 Zaległe leady dla Kierownika</h2>'
            f'<div class="male" style="margin-bottom:8px">Osoby, którym wysłaliśmy zaproszenie, a które nie dostały listu (nie starczyło normy). '
            f'Codziennie rano zanoszę Kierownikowi listę — agent pisze do nich NAJPIERW, w ramach normy listów. {info}</div>'
            f'{f"<ol>{lista}</ol>" if lista else ""}'
            f'<div class="akcje"><label class="male">Ile dziennie <input type="number" name="ile" min="1" max="30" value="{zalegle.ile_dziennie()}" style="width:70px"></label>'
            f'<button type="submit" class="glowny">Przygotuj od nowa i wyślij Kierownikowi</button></div></form>')


def panel_leadow() -> str:
    """Drugi agent: nocny dobór leadów do listów z bazy kontaktów -> kolejka listów w Kierowniku (z podglądem kolejki)."""
    import leady
    u, o, lo = leady.ustawienia(), leady.ostatni(), leady.liczniki_ocen()
    k = leady.kolejka(300)
    opcje = "".join(f'<option value="{e(m)}"{" selected" if m == u["model"] else ""}>{e(m)}</option>'
                    for m in ([u["model"]] if u["model"] not in ai.modele() else []) + ai.modele())
    sdk = "".join(f'<option value="{e(m)}"{" selected" if m == u["model_sdk"] else ""}>{e(m or "domyślny model Codexa")}</option>'
                  for m in [""] + ai.SDK_MODELE)
    if o:
        info = (f'Ostatni przebieg: {e(o.get("czas", ""))} ({e(o.get("zrodlo", ""))}, {e(o.get("model", ""))}, {o.get("minut", 0)} min) — '
                f'ocenionych {o.get("ocenionych", 0)}, dodanych do kolejki <b>{o.get("dodanych", 0)}</b>, błędów {o.get("bledow", 0)}; '
                f'w kolejce przed: {o.get("czeka_przed", 0)}, po: {o.get("czeka_po", 0)}. {e(o.get("uwaga", ""))}')
    else:
        info = "Agent jeszcze nie pracował."
    if k.get("blad"):
        lista = f'<div class="male zle">Nie udało się pobrać kolejki z Kierownika: {e(k["blad"])}</div>'
    else:
        li = "".join(f'<li><a href="{e(r["profile_url"])}" target="_blank">{e(r["name"] or r["profile_url"])}</a> '
                     f'<span class="male">{e(" · ".join(x for x in (r.get("position"), r.get("company"), r.get("powod")) if x))}</span></li>' for r in k.get("lista", []))
        lista = (f'<div class="male" style="margin:8px 0">Kolejka w Kierowniku: czeka <b>{k.get("czeka", 0)}</b> · wysłano z kolejki {k.get("wyslano", 0)} · '
                 f'pominięto {k.get("pominieto", 0)}. Kierownik daje agentowi GPT osoby od góry tej listy.</div>'
                 f'<details{" open" if li else ""}><summary style="cursor:pointer;font-weight:700">Lista czekających ({k.get("czeka", 0)})</summary><ol>{li}</ol></details>')
    return f"""<form method="post" action="/ui/leady" class="panel" style="border-top-color:#14532d"><h2>🎯 Leady do listów — nocny agent</h2>
<div class="male" style="margin-bottom:8px">Co noc (od godziny niżej) przeglądam kontakty z bazy Kierownika od najnowszych, oceniam stanowisko i firmę wybranym modelem
i dokładam zakwalifikowanych do kolejki listów, aż w kolejce czeka zadana liczba. <b>Nie wchodzę na LinkedIn.</b> Pomijam tych, którzy dostali list, byli oceniani przy listach,
sami pisali, mają teczkę albo już ich oceniłam (ocenionych dotąd {lo["ocenionych"]}, zakwalifikowanych {lo["zakwalifikowanych"]}).
Nowi ludzie w kontaktach pojawiają się po wgraniu świeżego Connections.csv do Kierownika.</div>
<div class="siatka"><div><label class="pl">Silnik</label><select name="silnik"><option value="api"{" selected" if u["silnik"] == "api" else ""}>API OpenAI (klucz, płatne za zapytanie)</option><option value="sdk"{" selected" if u["silnik"] == "sdk" else ""}>SDK — abonament ChatGPT (przez Codex)</option></select></div>
<div><label class="pl">Model (API)</label><select name="model">{opcje}</select></div>
<div><label class="pl">Model (SDK)</label><select name="model_sdk">{sdk}</select></div>
<div><label class="pl">Ile ma czekać w kolejce</label><input type="number" name="cel" min="1" max="2000" value="{u["cel"]}"></div>
<div><label class="pl">Najwyżej minut na przebieg</label><input type="number" name="minuty" min="1" max="180" value="{u["minuty"]}"></div>
<div><label class="pl">Osób na jedno zapytanie</label><input type="number" name="porcja" min="5" max="100" value="{u["porcja"]}"></div>
<div><label class="pl">Start w nocy od godziny</label><input type="number" name="godzina" min="0" max="23" value="{u["godzina"]}"></div></div>
<label class="pl" style="margin-top:12px">Prompt: kogo kwalifikujemy do listu</label><textarea name="prompt">{e(u["prompt"])}</textarea>
<div class="akcje"><button type="submit" class="glowny" name="teraz" value="1">Zapisz i szukaj teraz</button><button type="submit">Tylko zapisz</button>
<span class="male">{info}</span></div>{lista}</form>"""


# --------------------------------------------------------------- branże: szufladki „branża + rejon”

def _info_box(info: str) -> str:
    return (f'<div style="background:#eef6ee;border:1px solid #bcd9bc;padding:8px 12px;border-radius:6px;margin:0 0 14px;font-weight:600">{e(info)}</div>'
            if info else "")


def _kafel(liczba, opis: str) -> str:
    return (f'<div style="border:1px solid var(--linia);border-radius:8px;padding:8px 14px;min-width:110px"><b style="display:block;font-size:22px">{liczba}</b>'
            f'<span class="male" style="text-transform:uppercase;letter-spacing:.05em;font-size:11px">{opis}</span></div>')


def strona_branz(info: str = "") -> str:
    szuflady = branze.wszystkie()
    karty = "".join(
        f'<a href="/branze/{s["id"]}" class="panel" style="display:block;text-decoration:none;color:inherit;border-top-color:#2e7d6b">'
        f'<h2 style="margin-bottom:6px">🗂 {e(s["branza"])}{" — " + e(s["rejon"]) if s["rejon"] else ""}</h2>'
        f'<div style="display:flex;gap:10px;flex-wrap:wrap">{_kafel(s["firm"], "firm")}{_kafel(s["vipow"], "VIP-ów")}{_kafel(s["do_zaproszenia"], "do zaproszenia")}'
        f'{_kafel(s["zaproszonych"], "zaproszonych")}{_kafel(s["w_kontaktach"], "w kontaktach")}</div></a>' for s in szuflady)
    tresc = (f'<p><a href="/">← wszystkie teczki</a></p>{_info_box(info)}'
             '<form method="post" action="/ui/branze/nowa" class="panel"><h2>Branże — szufladki</h2>'
             '<div class="male" style="margin-bottom:8px">Jedna szufladka to branża w jednym rejonie, np. „Montownie — województwo łódzkie”. '
             'Wrzucasz do niej plik z firmami, a Analityczka z Detektywem znajdują ich VIP-ów, agent GPT wysyła im zaproszenia, a Ty zostajesz z gotową listą do ręcznych ofert.</div>'
             '<div style="display:flex;gap:10px;flex-wrap:wrap"><input type="text" name="branza" required maxlength="80" placeholder="Branża, np. Montownie" style="flex:1;min-width:200px;padding:8px;border:1px solid var(--linia);border-radius:8px">'
             '<input type="text" name="rejon" maxlength="80" placeholder="Rejon, np. województwo łódzkie" style="flex:1;min-width:200px;padding:8px;border:1px solid var(--linia);border-radius:8px">'
             '<button type="submit" class="glowny">+ Załóż szufladkę</button></div></form>'
             + (karty or '<div class="male">Nie ma jeszcze żadnej szufladki. Załóż pierwszą powyżej.</div>'))
    return _ramka(tresc)


def strona_szuflady(sid: int, info: str = "", status: str = "") -> str:
    s = branze.szuflada(sid)
    k = branze.liczniki(sid)
    firmy_, vipy_ = branze.firmy(sid), branze.vipy(sid, status)
    det = branze.stan_detektywa(sid)
    niewyslane = sum(1 for f in firmy_ if not f["wyslano"])
    if det and k["firm_wyslanych"]:
        przeszukane = det["gotowa"] + det["pusta"] + det["blad"]
        proc = round(100 * przeszukane / det["firm"]) if det["firm"] else 0
        postep = (f'<div class="panel" style="border-top-color:#6c3483"><b>Detektyw szuka VIP-ów:</b> przeszukano {przeszukane} z {det["firm"]} firm ({proc}%) · '
                  f'{"<b style=color:#17703f>pracuje…</b>" if det["czeka"] or det["w_toku"] else "skończył"}'
                  f'<div style="height:12px;border-radius:6px;background:#e5e5e5;overflow:hidden;margin-top:8px"><div style="height:100%;width:{proc}%;background:#6c3483"></div></div></div>')
    else:
        postep = ""
    def stan(v):
        if v["w_kontaktach"]:
            return '<span class="et" style="border-color:#17703f;color:#17703f;font-weight:700">w kontaktach</span>'
        if v["zaproszony"]:
            return '<span class="et">zaproszony</span>'
        if v["odrzucony"]:
            return f'<span class="et" style="border-color:#a32020;color:#a32020" title="{e(v["powod"])}">odrzucony</span><div class="male">{e(v["powod"])}</div>'
        return '<span class="male">czeka na zaproszenie</span>'
    wiersze = "".join(
        f'<tr><td><b>{e(v["nazwa"])}</b><div class="male">{e(v["stanowisko"])}</div></td><td>{e(v["firma"])}</td>'
        f'<td><a href="{e(v["linkedin_url"])}" target="_blank" rel="noopener">profil</a></td><td>{stan(v)}</td></tr>' for v in vipy_)
    tab_vip = (f'<table style="width:100%;border-collapse:collapse"><thead><tr><th align="left">VIP</th><th align="left">Firma</th><th align="left">LinkedIn</th><th align="left">Status</th></tr></thead>'
               f'<tbody>{wiersze}</tbody></table>') if vipy_ else '<div class="male">Jeszcze nikogo — zleć Detektywowi szukanie VIP-ów (przycisk wyżej).</div>'
    if status in ("kontakty", "po_specjalnej"):
        def spec(v):
            st = v["specjalny"]
            if st == "oczekuje":
                return '<span class="et" style="border-color:#6c3483;color:#6c3483">czeka u agenta</span>'
            if st == "wyslano":
                return '<span class="et" style="border-color:#17703f;color:#17703f">wysłano specjalnie</span>'
            if st == "pominieto":
                return f'<span class="et" style="border-color:#a32020;color:#a32020">pominięty</span><div class="male">{e(v["specjalny_powod"])}</div>'
            return ""
        wiersze_s = "".join(
            f'<tr><td><input type="checkbox" name="vip" value="{v["id"]}"></td><td><b>{e(v["nazwa"])}</b><div class="male">{e(v["stanowisko"])}</div></td><td>{e(v["firma"])}</td>'
            f'<td><a href="{e(v["linkedin_url"])}" target="_blank" rel="noopener">profil</a></td><td>{stan(v)}</td>'
            f'<td>{spec(v)}</td></tr>' for v in vipy_)
        tab_vip = f"""<form method="post" action="/ui/branze/{sid}/specjalna" id="specjalna">
<div class="panel" style="border-top-color:#6c3483"><h3>Wysyłka specjalna — agent pisze do tych osób sam, ale tylko według specjalnej instrukcji z tego pola</h3>
<div class="male" style="margin-bottom:8px">VIP-y z szufladki nie dostają zwykłych, automatycznych listów (tych wysyłanych wszystkim). Agent GPT pisze do nich sam, ale wyłącznie na podstawie instrukcji, którą wpisujesz tutaj
(np. specjalny produkt, film, oferta tylko dla nich). Prompt zapisuje się dla całej szufladki. Zaznacz osoby i kliknij „Wyślij zaznaczonych” — trafią do kolejki specjalnej. Agent GPT wyśle je, gdy wpiszesz w czacie komendę „/spec N” (np. „/spec 10”).</div>
<textarea name="prompt" rows="8" style="width:100%" placeholder="Np.: Napisz krótką, osobistą wiadomość. Zaproponuj film o kontroli montażu (link: …) i wspomnij o …">{e(s["prompt_specjalny"])}</textarea>
<div class="akcje"><button type="submit" name="akcja" value="zapisz">Zapisz prompt</button>
<button type="submit" name="akcja" value="wyslij" class="glowny">Wyślij zaznaczonych specjalną procedurą</button>
<label class="male"><input type="checkbox" onclick="document.querySelectorAll('input[name=vip]').forEach(c=>c.checked=this.checked)"> zaznacz wszystkich</label></div></div>
<table style="width:100%;border-collapse:collapse"><thead><tr><th align="left" style="font-size:.8em;max-width:90px">wyślij specjalną procedurą</th><th align="left">VIP</th><th align="left">Firma</th><th align="left">LinkedIn</th><th align="left">Status</th><th align="left">Wysyłka specjalna</th></tr></thead>
<tbody>{wiersze_s}</tbody></table></form>""" if vipy_ else '<div class="male">Jeszcze nikt z VIP-ów nie jest w kontaktach.</div>'
    opcje = (("", "wszyscy", k["vipow"]), ("do_zaproszenia", "czekają na zaproszenie", k["do_zaproszenia"]),
             ("zaproszeni", "zaproszeni (jeszcze nie w kontaktach)", k["zaproszonych"] - k["w_kontaktach"]), ("odrzuceni", "odrzuceni przy wysyłce zaproszeń", k["odrzuconych"]),
             ("kontakty", "już w kontaktach", k["w_kontaktach"]), ("po_specjalnej", "po specjalnej wysyłce", k["po_specjalnej"]))
    filtry = ('<div style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px">' + "".join(
        f'<a href="/branze/{sid}?status={kod}#vipy" style="padding:4px 12px;border:1px solid #111;border-radius:14px;text-decoration:none;'
        f'{"background:#111;color:#fff;" if kod == status else "color:#111;"}">{e(nazwa)} ({n})</a>' for kod, nazwa, n in opcje) +
        (f'<a href="/branze/{sid}/vipy.csv?status={status}" style="padding:4px 12px;color:#111">⬇ pobierz tę listę (CSV)</a>' if status else "") + '</div>')
    pliki_f = "".join(f'<li>{e(f["firma"])}{"" if f["wyslano"] else " <span class=male>(jeszcze nie zlecona)</span>"}</li>' for f in firmy_[:300])
    odsw = f'ostatnie sprawdzenie: {e(s["sync_ts"][:16])}' if s["sync_ts"] else "jeszcze nie sprawdzano"
    tresc = f"""<p><a href="/branze">← wszystkie szufladki</a></p>{_info_box(info)}
<div class="panel" style="border-top-color:#2e7d6b"><h2>🗂 {e(s["branza"])}{" — " + e(s["rejon"]) if s["rejon"] else ""}</h2>
<div style="display:flex;gap:10px;flex-wrap:wrap">{_kafel(k["firm"], "firm w pliku")}{_kafel(k["vipow"], "VIP-ów znaleziono")}{_kafel(k["do_zaproszenia"], "do zaproszenia")}{_kafel(k["zaproszonych"], "zaproszonych")}{_kafel(k["w_kontaktach"], "już w kontaktach")}</div>
<div class="male" style="margin-top:8px">Agent GPT wysyła VIP-om z tej szufladki wyłącznie zaproszenia. Listy i oferty agent pisze im sam, ale tylko według Twojego specjalnego promptu („wysyłka specjalna” w zakładce „już w kontaktach”). Statusy: {odsw}.
Przyjęcie zaproszenia Kierownik zauważa po odświeżeniu listy kontaktów albo gdy agent zgłosi osobę jako kontakt.</div></div>
{postep}
<form method="post" action="/ui/branze/{sid}/wrzuc" enctype="multipart/form-data" class="panel"><h2>1. Wrzuć plik z firmami</h2>
<div class="male" style="margin-bottom:8px">CSV, XLS lub XLSX. Kolumnę z nazwą firmy rozpoznaję po nagłówku (firma, nazwa, company…), inaczej biorę pierwszą kolumnę; miasto (jeśli jest kolumna) dopisuję do nazwy.</div>
<input type="file" name="pliki" multiple required accept=".csv,.xls,.xlsx"><div class="akcje"><button type="submit" class="glowny">Wczytaj firmy do szufladki</button></div></form>
<div class="panel"><h2>2. Znajdź VIP-ów i zaproś ich</h2>
<div class="male" style="margin-bottom:8px">Analityczka zleca Detektywowi firmy z pliku → Detektyw zwraca adresy LinkedIn VIP-ów → Analityczka przekazuje je Kierownikowi → agent GPT wysyła zaproszenia.</div>
<div class="akcje"><form method="post" action="/ui/branze/{sid}/szukaj"><button class="glowny"{" disabled" if not niewyslane else ""}>Zleć Detektywowi szukanie VIP-ów ({niewyslane} firm)</button></form>
<form method="post" action="/ui/branze/{sid}/odswiez"><button>Odśwież statusy (zaproszeni / w kontaktach)</button></form>
<a class="przycisk" href="/branze/{sid}/vipy.csv" style="padding:8px 14px;border:1px solid #111;border-radius:6px;text-decoration:none;color:#111">Pobierz listę VIP-ów (CSV)</a></div></div>
<div class="panel" id="vipy"><h2>VIP-y w szufladce ({len(vipy_)}{"" if not status else " z " + str(k["vipow"])})</h2>{filtry}{tab_vip}</div>
<details class="panel"><summary style="cursor:pointer;font-weight:700">Firmy w szufladce ({k["firm"]})</summary><ul>{pliki_f or "<li class=male>brak</li>"}</ul></details>
<form method="post" action="/ui/branze/{sid}/usun" onsubmit="return confirm('Usunąć całą szufladkę razem z listą firm i VIP-ów? Zaproszenia już wysłane zostają.')"><button style="border-color:#a32020;color:#a32020">Usuń szufladkę</button></form>"""
    return _ramka(tresc)


def karta_branz() -> str:
    sz = branze.wszystkie()
    podsum = f'szufladek: {len(sz)} · VIP-ów: {sum(s["vipow"] for s in sz)} · w kontaktach: {sum(s["w_kontaktach"] for s in sz)}'
    return (f'<div class="panel" style="border-top-color:#2e7d6b"><h2>🗂 Branże</h2><div class="male" style="margin-bottom:8px">'
            f'Szufladki „branża + rejon” z VIP-ami do ręcznych ofert — {podsum}.</div>'
            '<div class="akcje"><a href="/branze" style="font-weight:700">Otwórz branże →</a></div></div>')
