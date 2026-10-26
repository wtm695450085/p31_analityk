"""Buduje workflow n8n agent_Darwin Analityka i zapisuje do katalogu danych n8n.

Użycie (na VPS):
    python3 n8n/build_workflow.py            # zapis do /apps/n8n_insurance_rag/data/analityk/
    docker exec n8n-n8n-1 n8n import:workflow --separate --input=/home/node/.n8n/analityk/
    docker exec n8n-n8n-1 n8n publish:workflow --id=analitykHermesTick && docker restart n8n-n8n-1
Token agent_Darwin jest brany z .env projektu — plik wynikowy zawiera sekret, nie commituj go.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/apps/n8n_insurance_rag/data/analityk")
ENV = dict(l.split("=", 1) for l in (ROOT / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
CFG = "$('Konfiguracja').first().json"


def node(name, type_, version, params, pos, **extra):
    return {"id": name.lower().replace(" ", "-")[:36], "name": name, "type": f"n8n-nodes-base.{type_}",
            "typeVersion": version, "position": pos, "parameters": params, **extra}


nodes = [
    node("Co 30 minut", "scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "cronExpression", "expression": "*/30 * * * *"}]}}, [0, 0]),
    node("Uruchom ręcznie", "manualTrigger", 1, {}, [0, 200]),
    node("Konfiguracja", "set", 3.4, {"assignments": {"assignments": [
        {"id": "a1", "name": "base_url", "value": "http://analityk:8000", "type": "string"},
        {"id": "a2", "name": "token", "value": ENV["HERMES_TOKEN"], "type": "string"}]}, "options": {}}, [220, 100]),
    node("agent_Darwin: teczki i oceny", "httpRequest", 4.2, {
        "method": "POST", "url": f"={{{{ {CFG}.base_url }}}}/api/hermes/tick", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Hermes-Token", "value": f"={{{{ {CFG}.token }}}}"}]},
        "options": {"timeout": 900000}}, [440, 100]),
    node("Podsumowanie", "code", 2, {"jsCode": """// Jedna pozycja z czytelnym podsumowaniem przebiegu — widać ją na liście wykonań.
const r = $input.first().json;
return [{ json: {
  przebieg_ok: r.ok,
  czas: r.czas,
  pobrano_z_kierownika: r.pobrano,
  nowych_teczek: r.nowych_teczek,
  nowych_wiadomosci: r.nowych_wiadomosci,
  ocenionych_teraz: r.ocenionych,
  bledow: r.bledow,
  uwaga: r.uwaga || '',
  teczek_razem: r.teczek,
  pozytywnych: r.pozytywnych,
  czeka_na_ocene: r.do_oceny,
}}];"""}, [660, 100]),
    node("Opis agent_Darwin", "stickyNote", 1, {"width": 460, "height": 300, "content": """## Analityk · agent_Darwin — teczki i oceny odpowiedzi

Co 30 minut agent_Darwin (ten workflow) woła **https://analityk.sigmaquality.pl** (w sieci n8n: `http://analityk:8000`) i:

* pobiera z **Kierownika** wszystkie odpowiedzi z LinkedIn (CRM) razem z tym, co do osoby wysłano,
* zakłada **teczkę na każdą osobę** i dopisuje wszystko, co przyszło i co wysłaliśmy,
* ocenia modelem OpenAI (wybranym na stronie Analityka), kto odpowiedział **pozytywnie** na list: odezwie się, podał termin, zapamięta kontakt.

Kierownik może też wysłać odpowiedzi sam (CRM → Zespół → „Wyślij do analityczki”). Przebieg ręczny: „Uruchom ręcznie”."""}, [0, -380]),
]
conns = {"Co 30 minut": {"main": [[{"node": "Konfiguracja", "type": "main", "index": 0}]]},
         "Uruchom ręcznie": {"main": [[{"node": "Konfiguracja", "type": "main", "index": 0}]]},
         "Konfiguracja": {"main": [[{"node": "agent_Darwin: teczki i oceny", "type": "main", "index": 0}]]},
         "agent_Darwin: teczki i oceny": {"main": [[{"node": "Podsumowanie", "type": "main", "index": 0}]]}}
wf = {"id": "analitykHermesTick", "name": "Analityk · agent_Darwin — teczki i oceny odpowiedzi (co 30 min)",
      "description": "agent_Darwin Analityka: pobiera odpowiedzi z LinkedIn od Kierownika, zakłada teczki i ocenia, kto odpowiedział pozytywnie.", "active": False,
      "nodes": nodes, "connections": conns, "pinData": {}, "tags": [],
      "settings": {"executionOrder": "v1", "timezone": "Europe/Warsaw", "saveManualExecutions": True,
                   "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all", "executionTimeout": 900}}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "analitykHermesTick.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print("zapisano", OUT / "analitykHermesTick.json")


# ---- druga robota agent_Darwin: odprawa strategiczna codziennie o 2:00 w nocy (plan gotowy rano)
nodes2 = [
    node("Codziennie o 2:00", "scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "cronExpression", "expression": "0 2 * * *"}]}}, [0, 0]),
    node("Uruchom ręcznie", "manualTrigger", 1, {}, [0, 200]),
    node("Konfiguracja", "set", 3.4, {"assignments": {"assignments": [
        {"id": "a1", "name": "base_url", "value": "http://analityk:8000", "type": "string"},
        {"id": "a2", "name": "token", "value": ENV["HERMES_TOKEN"], "type": "string"}]}, "options": {}}, [220, 100]),
    node("agent_Darwin: świeże dane", "httpRequest", 4.2, {
        "method": "POST", "url": f"={{{{ {CFG}.base_url }}}}/api/hermes/tick", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Hermes-Token", "value": f"={{{{ {CFG}.token }}}}"}]},
        "options": {"timeout": 900000}}, [440, 100]),
    node("agent_Darwin: odprawa strategiczna", "httpRequest", 4.2, {
        "method": "POST", "url": f"={{{{ {CFG}.base_url }}}}/api/hermes/odprawa", "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "X-Hermes-Token", "value": f"={{{{ {CFG}.token }}}}"}]},
        "options": {"timeout": 60000}}, [660, 100]),
    node("Opis odprawy", "stickyNote", 1, {"width": 460, "height": 260, "content": """## Analityk · odprawa strategiczna o 2:00

Codziennie o 2:00 agent_Darwin najpierw odświeża dane (teczki, odpowiedzi z LinkedIn, poczta), potem uruchamia **odprawę strategiczną**:
analiza wszystkich teczek, spotkania i rozmowy na dziś i jutro, pilne sprawy, propozycje, zaległe telefony. Telefony z planu trafiają na **listę pilnego kontaktu**.
Odprawa trwa kilka minut w tle — wynik jest na https://analityk.sigmaquality.pl/odprawa. Zaległe telefony (brak wpisu w teczce) wracają następnego dnia."""}, [0, -340]),
]
conns2 = {"Codziennie o 2:00": {"main": [[{"node": "Konfiguracja", "type": "main", "index": 0}]]},
          "Uruchom ręcznie": {"main": [[{"node": "Konfiguracja", "type": "main", "index": 0}]]},
          "Konfiguracja": {"main": [[{"node": "agent_Darwin: świeże dane", "type": "main", "index": 0}]]},
          "agent_Darwin: świeże dane": {"main": [[{"node": "agent_Darwin: odprawa strategiczna", "type": "main", "index": 0}]]}}
wf2 = {"id": "analitykHermesOdprawa", "name": "Analityk · agent_Darwin — odprawa strategiczna (codziennie 2:00)",
       "description": "Codziennie o 2:00: świeże dane i odprawa strategiczna Analityka — plan na rano.", "active": False,
       "nodes": nodes2, "connections": conns2, "pinData": {}, "tags": [],
       "settings": {"executionOrder": "v1", "timezone": "Europe/Warsaw", "saveManualExecutions": True,
                    "saveDataSuccessExecution": "all", "saveDataErrorExecution": "all", "executionTimeout": 1200}}
(OUT / "analitykHermesOdprawa.json").write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding="utf-8")
print("zapisano", OUT / "analitykHermesOdprawa.json")
