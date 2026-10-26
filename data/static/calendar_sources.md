# Źródła kalendarza (calendar.csv)

Wygenerowane przez `python -m src.data.fetch_static --only calendar` z `src/data/calendar_data.py`.
Okresy oznaczone jako **niepewne** nie zostały potwierdzone w dokumencie źródłowym (w calendar.csv: `{uczelnia}_certain = False`).

## Źródła

- `holidays` – Ustawa z 18.01.1951 o dniach wolnych od pracy (z Wigilią od 2025), biblioteka Python `holidays`. <https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU19510040028>
- `school_rule` – Rozporządzenie MEN z 11.08.2017 w sprawie organizacji roku szkolnego (Dz.U. 2023 poz. 1211), § 2–3: zimowa przerwa świąteczna 23–31 XII, wiosenna od czwartku przed Wielkanocą do wtorku po niej, zakończenie zajęć w ostatni piątek czerwca. <https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20230001211>
- `ferie` – Portal Oświatowy – ferie zimowe 2027 (komunikat MEN, § 3 ust. 1 pkt 2 rozporządzenia): mazowieckie 1–14 II 2027. <https://www.portaloswiatowy.pl/komunikaty-men-i-cke/-ferie-zimowe-2027-terminy-na-rok-szkolny-20262027-26395.html>
- `uw` – Postanowienie nr 1 Rektora UW z 30.01.2026 w sprawie organizacji roku akademickiego 2026/2027 (Monitor UW 2026 poz. 30). Użyto harmonogramu ogólnego; Wydziały Chemii, Fizyki i MIM mają osobny (zał. 1: blok I semestru letniego od 22.02, sesja letnia 14–27.06). W dokumencie literówka „07.07.2027 – 24.01.2027” – poprawnie 07.01.2027 (jak w zał. 1). <https://monitor.uw.edu.pl/Lists/Uchway/Attachments/7679/M.2026.30.Post.1.pdf>
- `pw` – Zarządzenie nr 24/2026 Rektora PW z 21.05.2026 w sprawie szczegółowego harmonogramu roku akademickiego 2026/2027. Dzień PW 15.11.2026 wypada w niedzielę; 13.11.2026 (pt) zajęcia wg planu środy. <https://www.wip.pw.edu.pl/content/download/6398/35908/file/24_2026_ZARZ%C4%84DZENIE%20Rektora_harmonogram_roku_akad_2026-27.pdf>
- `wum` – Zarządzenie nr 90/2026 Rektora WUM z 13.04.2026 w sprawie organizacji roku akademickiego 2026/2027 (uchyla zarz. 72/2026). <https://lekarski.wum.edu.pl/sites/wl.wum.edu.pl/files/zarzadzenie_rektora-90-2026_zmiana_-podzial_roku_akademickiego_2026_2027-1.pdf>
- `wum_rector_day` – Wydział Lekarski WUM – plan zajęć, powołanie na zarz. 156/2026 (dzień rektorski 5.10.2026); dokumentu zarządzenia nie zweryfikowano. <https://lekarski.wum.edu.pl/node/759>
- `sgh_sessions` – SGH – strona „Organizacja roku akademickiego” (terminy sesji 2026/2027 podane przy zjazdach). Pełny dokument (bap.sgh.waw.pl/d/39927/5/) był niedostępny. <https://www.sgh.waw.pl/organizacja-roku-akademickiego>
- `sgh_estimate` – Szacunek – zajęcia i przerwy SGH nie potwierdzone (ułożone wg sesji SGH, zjazdów niestacjonarnych 20.02–13.06.2027 i typowych przerw innych uczelni). <https://bap.sgh.waw.pl/d/39927/5/>

## Okresy

| kalendarz | rodzaj | od | do | opis | źródło | pewne |
|---|---|---|---|---|---|---|
| school | break | 2026-12-23 | 2026-12-31 | zimowa przerwa świąteczna | `school_rule` | tak |
| school | break | 2027-02-01 | 2027-02-14 | ferie zimowe (mazowieckie) | `ferie` | tak |
| school | break | 2027-03-25 | 2027-03-30 | wiosenna przerwa świąteczna | `school_rule` | tak |
| school | break | 2027-06-26 | 2027-06-30 | wakacje letnie | `school_rule` | tak |
| uw | classes | 2026-10-02 | 2026-12-20 | zajęcia (bloki I–III) | `uw` | tak |
| uw | break | 2026-12-21 | 2027-01-06 | wakacje zimowe | `uw` | tak |
| uw | classes | 2027-01-07 | 2027-01-24 | zajęcia (blok III c.d.) | `uw` | tak |
| uw | exams | 2027-01-25 | 2027-02-07 | sesja zimowa | `uw` | tak |
| uw | break | 2027-02-08 | 2027-02-14 | przerwa międzysemestralna | `uw` | tak |
| uw | classes | 2027-02-15 | 2027-06-06 | zajęcia semestru letniego | `uw` | tak |
| uw | break | 2027-03-25 | 2027-03-30 | wakacje wiosenne | `uw` | tak |
| uw | exams | 2027-06-07 | 2027-06-27 | sesja letnia | `uw` | tak |
| uw | break | 2027-06-28 | 2027-06-30 | wakacje letnie | `uw` | tak |
| uw | free_day | 2026-10-01 | 2026-10-01 | inauguracja roku | `uw` | tak |
| uw | free_day | 2027-05-02 | 2027-05-02 | dzień wolny | `uw` | tak |
| uw | free_day | 2027-05-07 | 2027-05-08 | juwenalia | `uw` | tak |
| uw | free_day | 2027-05-28 | 2027-05-28 | dzień wolny | `uw` | tak |
| pw | free_day | 2026-10-01 | 2026-10-01 | inauguracja roku | `pw` | tak |
| pw | classes | 2026-10-02 | 2026-12-23 | zajęcia semestru zimowego | `pw` | tak |
| pw | break | 2026-12-24 | 2027-01-06 | wakacje zimowe | `pw` | tak |
| pw | classes | 2027-01-07 | 2027-01-31 | zajęcia semestru zimowego | `pw` | tak |
| pw | exams | 2027-02-01 | 2027-02-14 | sesja zimowa | `pw` | tak |
| pw | break | 2027-02-15 | 2027-02-21 | okres rejestracyjny | `pw` | tak |
| pw | classes | 2027-02-22 | 2027-06-16 | zajęcia semestru letniego | `pw` | tak |
| pw | break | 2027-03-25 | 2027-03-30 | wakacje wiosenne | `pw` | tak |
| pw | free_day | 2027-05-14 | 2027-05-14 | juwenalia | `pw` | tak |
| pw | free_day | 2027-05-28 | 2027-05-28 | dzień wolny | `pw` | tak |
| pw | exams | 2027-06-17 | 2027-06-30 | sesja letnia | `pw` | tak |
| sgh | classes | 2026-10-01 | 2027-01-24 | zajęcia semestru zimowego | `sgh_estimate` | **niepewne** |
| sgh | break | 2026-12-23 | 2027-01-06 | przerwa świąteczna | `sgh_estimate` | **niepewne** |
| sgh | exams | 2027-01-25 | 2027-02-07 | sesja zimowa (I termin) | `sgh_sessions` | tak |
| sgh | break | 2027-02-08 | 2027-02-12 | przerwa międzysemestralna | `sgh_estimate` | **niepewne** |
| sgh | resit | 2027-02-13 | 2027-02-19 | sesja zimowa (II termin) | `sgh_sessions` | tak |
| sgh | classes | 2027-02-20 | 2027-06-13 | zajęcia semestru letniego | `sgh_estimate` | **niepewne** |
| sgh | break | 2027-03-25 | 2027-03-30 | przerwa wielkanocna | `sgh_estimate` | **niepewne** |
| sgh | exams | 2027-06-14 | 2027-06-27 | sesja letnia (I termin) | `sgh_sessions` | tak |
| sgh | break | 2027-06-28 | 2027-06-30 | wakacje letnie | `sgh_estimate` | **niepewne** |
| wum | classes | 2026-10-01 | 2026-12-20 | zajęcia | `wum` | tak |
| wum | free_day | 2026-10-05 | 2026-10-05 | dzień rektorski | `wum_rector_day` | **niepewne** |
| wum | break | 2026-12-21 | 2027-01-03 | przerwa świąteczna | `wum` | tak |
| wum | classes | 2027-01-04 | 2027-01-31 | zajęcia | `wum` | tak |
| wum | exams | 2027-02-01 | 2027-02-07 | sesja zimowa | `wum` | tak |
| wum | break | 2027-02-08 | 2027-02-14 | przerwa semestralna | `wum` | tak |
| wum | resit | 2027-02-15 | 2027-02-21 | sesja poprawkowa | `wum` | tak |
| wum | classes | 2027-02-22 | 2027-03-24 | zajęcia | `wum` | tak |
| wum | break | 2027-03-25 | 2027-03-31 | przerwa świąteczna | `wum` | tak |
| wum | classes | 2027-04-01 | 2027-06-13 | zajęcia | `wum` | tak |
| wum | break | 2027-06-14 | 2027-06-20 | przerwa na przygotowanie do sesji | `wum` | tak |
| wum | exams | 2027-06-21 | 2027-06-30 | sesja letnia | `wum` | tak |
