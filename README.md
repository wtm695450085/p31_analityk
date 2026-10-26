# Analityk — analityk.sigmaquality.pl

Aplikacja w kontenerze (`p31_analityk`, 127.0.0.1:8531). FastAPI + SQLite + **Agent na n8n**, jak Kierownik (p30) i Wywiadowca (p14).

## Co robi
1. **Zakłada teczki** na każdą osobę, która odpisała na wiadomość z LinkedIn. W teczce jest wszystko: co przyszło od osoby
   i co do niej wysłaliśmy (listy, zaproszenia, nasze odpowiedzi z CRM). Ta sama osoba pod kilkoma adresami profilu = jedna teczka (łączenie po nazwisku).
2. **Ocenia**, czy odpowiedź na nasz list jest **pozytywna** (odezwie się, podała termin np. „koniec października”, zapamięta kontakt,
   zainteresowanie, prosi o kontakt): rodzaj, termin kontaktu, streszczenie, następny krok, ciepłość 0–6. Bez naszego listu w teczce
   odpowiedź nie liczy się jako pozytywna (`brak_listu`). Model i kryteria ustawia się na stronie.

## Przepływ danych
- **Kierownik → Analityk (push):** CRM → Zespół → „Wyślij do analityczki” → `POST /api/kierownik/odpowiedzi` (`X-Kierownik-Token`).
- **Agent (pull, co 30 min):** workflow n8n `analitykHermesTick` woła `POST http://analityk:8000/api/hermes/tick` (`X-Hermes-Token`);
  Analityk pobiera z Kierownika `GET /api/executor/replies` (token wykonawcy), zakłada teczki i ocenia nowe/zmienione.
- Duplikaty odsiewa hash wiadomości, więc obie drogi są bezpieczne.

## Dostęp
Strona za hasłem HTTP (nginx, `/etc/nginx/.htpasswd-analityk`). `/api/` jest bez hasła HTTP — chronią go tokeny.

## Wdrożenie
    cd /apps/p31_analityk && docker compose up -d --build
    python3 n8n/build_workflow.py
    docker exec n8n-n8n-1 n8n import:workflow --separate --input=/home/node/.n8n/analityk/
    docker exec n8n-n8n-1 n8n publish:workflow --id=analitykHermesTick && docker restart n8n-n8n-1

## .env
`OPENAI_API_KEY`, `OPENAI_MODEL`, `HERMES_TOKEN`, `KIEROWNIK_PUSH_TOKEN` (= `ANALITYK_TOKEN` w p30_kierownik/.env),
`KIEROWNIK_URL` (http://kierownik:8000), `KIEROWNIK_EXECUTOR_TOKEN` (= `EXECUTOR_TOKEN` z p30).
