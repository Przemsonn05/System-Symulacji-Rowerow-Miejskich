"""Kalendarz szkolny i akademicki 2026/2027 (Warszawa) - okresy ze zrodlami.

Swieta ustawowe pochodza z biblioteki `holidays` (ustawa o dniach wolnych od pracy).
Tu sa tylko okresy, ktorych biblioteka nie zna. Kazdy okres ma zrodlo i flage
`certain`: False = data nie potwierdzona w dokumencie zrodlowym (szacunek).

Rodzaje okresow uczelni (kolumna {uczelnia}_period w calendar.csv):
  classes   zajecia dydaktyczne
  exams     sesja egzaminacyjna
  resit     sesja poprawkowa
  break     przerwa / wakacje
  free_day  dzien wolny od zajec (dzien rektorski, inauguracja, juwenalia)
Pozniejszy wpis na liscie nadpisuje wczesniejszy dla tych samych dni.
"""

import datetime as dt

D = dt.date

SOURCES = {
    "holidays": (
        "Ustawa z 18.01.1951 o dniach wolnych od pracy (z Wigilią od 2025), biblioteka Python `holidays`",
        "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU19510040028",
    ),
    "school_rule": (
        "Rozporządzenie MEN z 11.08.2017 w sprawie organizacji roku szkolnego (Dz.U. 2023 poz. 1211), § 2–3: "
        "zimowa przerwa świąteczna 23–31 XII, wiosenna od czwartku przed Wielkanocą do wtorku po niej, "
        "zakończenie zajęć w ostatni piątek czerwca",
        "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20230001211",
    ),
    "ferie": (
        "Portal Oświatowy – ferie zimowe 2027 (komunikat MEN, § 3 ust. 1 pkt 2 rozporządzenia): mazowieckie 1–14 II 2027",
        "https://www.portaloswiatowy.pl/komunikaty-men-i-cke/-ferie-zimowe-2027-terminy-na-rok-szkolny-20262027-26395.html",
    ),
    "uw": (
        "Postanowienie nr 1 Rektora UW z 30.01.2026 w sprawie organizacji roku akademickiego 2026/2027 "
        "(Monitor UW 2026 poz. 30). Użyto harmonogramu ogólnego; Wydziały Chemii, Fizyki i MIM mają osobny "
        "(zał. 1: blok I semestru letniego od 22.02, sesja letnia 14–27.06). W dokumencie literówka "
        "„07.07.2027 – 24.01.2027” – poprawnie 07.01.2027 (jak w zał. 1)",
        "https://monitor.uw.edu.pl/Lists/Uchway/Attachments/7679/M.2026.30.Post.1.pdf",
    ),
    "pw": (
        "Zarządzenie nr 24/2026 Rektora PW z 21.05.2026 w sprawie szczegółowego harmonogramu roku akademickiego "
        "2026/2027. Dzień PW 15.11.2026 wypada w niedzielę; 13.11.2026 (pt) zajęcia wg planu środy",
        "https://www.wip.pw.edu.pl/content/download/6398/35908/file/24_2026_ZARZ%C4%84DZENIE%20Rektora_harmonogram_roku_akad_2026-27.pdf",
    ),
    "wum": (
        "Zarządzenie nr 90/2026 Rektora WUM z 13.04.2026 w sprawie organizacji roku akademickiego 2026/2027 "
        "(uchyla zarz. 72/2026)",
        "https://lekarski.wum.edu.pl/sites/wl.wum.edu.pl/files/zarzadzenie_rektora-90-2026_zmiana_-podzial_roku_akademickiego_2026_2027-1.pdf",
    ),
    "wum_rector_day": (
        "Wydział Lekarski WUM – plan zajęć, powołanie na zarz. 156/2026 (dzień rektorski 5.10.2026); "
        "dokumentu zarządzenia nie zweryfikowano",
        "https://lekarski.wum.edu.pl/node/759",
    ),
    "sgh_sessions": (
        "SGH – strona „Organizacja roku akademickiego” (terminy sesji 2026/2027 podane przy zjazdach). "
        "Pełny dokument (bap.sgh.waw.pl/d/39927/5/) był niedostępny",
        "https://www.sgh.waw.pl/organizacja-roku-akademickiego",
    ),
    "sgh_estimate": (
        "Szacunek – zajęcia i przerwy SGH nie potwierdzone (ułożone wg sesji SGH, zjazdów niestacjonarnych "
        "20.02–13.06.2027 i typowych przerw innych uczelni)",
        "https://bap.sgh.waw.pl/d/39927/5/",
    ),
}

UNIVERSITIES = ["uw", "pw", "sgh", "wum"]


def P(calendar, kind, start, end, label, source, certain=True):
    return {
        "calendar": calendar,
        "kind": kind,
        "start": start,
        "end": end,
        "label": label,
        "source": source,
        "certain": certain,
    }


PERIODS = [
    # --- szkoly (mazowieckie) -------------------------------------------------
    P("school", "break", D(2026, 12, 23), D(2026, 12, 31), "zimowa przerwa świąteczna", "school_rule"),
    P("school", "break", D(2027, 2, 1), D(2027, 2, 14), "ferie zimowe (mazowieckie)", "ferie"),
    P("school", "break", D(2027, 3, 25), D(2027, 3, 30), "wiosenna przerwa świąteczna", "school_rule"),
    P("school", "break", D(2027, 6, 26), D(2027, 6, 30), "wakacje letnie", "school_rule"),
    # --- Uniwersytet Warszawski -----------------------------------------------
    P("uw", "classes", D(2026, 10, 2), D(2026, 12, 20), "zajęcia (bloki I–III)", "uw"),
    P("uw", "break", D(2026, 12, 21), D(2027, 1, 6), "wakacje zimowe", "uw"),
    P("uw", "classes", D(2027, 1, 7), D(2027, 1, 24), "zajęcia (blok III c.d.)", "uw"),
    P("uw", "exams", D(2027, 1, 25), D(2027, 2, 7), "sesja zimowa", "uw"),
    P("uw", "break", D(2027, 2, 8), D(2027, 2, 14), "przerwa międzysemestralna", "uw"),
    P("uw", "classes", D(2027, 2, 15), D(2027, 6, 6), "zajęcia semestru letniego", "uw"),
    P("uw", "break", D(2027, 3, 25), D(2027, 3, 30), "wakacje wiosenne", "uw"),
    P("uw", "exams", D(2027, 6, 7), D(2027, 6, 27), "sesja letnia", "uw"),
    P("uw", "break", D(2027, 6, 28), D(2027, 6, 30), "wakacje letnie", "uw"),
    P("uw", "free_day", D(2026, 10, 1), D(2026, 10, 1), "inauguracja roku", "uw"),
    P("uw", "free_day", D(2027, 5, 2), D(2027, 5, 2), "dzień wolny", "uw"),
    P("uw", "free_day", D(2027, 5, 7), D(2027, 5, 8), "juwenalia", "uw"),
    P("uw", "free_day", D(2027, 5, 28), D(2027, 5, 28), "dzień wolny", "uw"),
    # --- Politechnika Warszawska ----------------------------------------------
    P("pw", "free_day", D(2026, 10, 1), D(2026, 10, 1), "inauguracja roku", "pw"),
    P("pw", "classes", D(2026, 10, 2), D(2026, 12, 23), "zajęcia semestru zimowego", "pw"),
    P("pw", "break", D(2026, 12, 24), D(2027, 1, 6), "wakacje zimowe", "pw"),
    P("pw", "classes", D(2027, 1, 7), D(2027, 1, 31), "zajęcia semestru zimowego", "pw"),
    P("pw", "exams", D(2027, 2, 1), D(2027, 2, 14), "sesja zimowa", "pw"),
    P("pw", "break", D(2027, 2, 15), D(2027, 2, 21), "okres rejestracyjny", "pw"),
    P("pw", "classes", D(2027, 2, 22), D(2027, 6, 16), "zajęcia semestru letniego", "pw"),
    P("pw", "break", D(2027, 3, 25), D(2027, 3, 30), "wakacje wiosenne", "pw"),
    P("pw", "free_day", D(2027, 5, 14), D(2027, 5, 14), "juwenalia", "pw"),
    P("pw", "free_day", D(2027, 5, 28), D(2027, 5, 28), "dzień wolny", "pw"),
    P("pw", "exams", D(2027, 6, 17), D(2027, 6, 30), "sesja letnia", "pw"),
    # --- SGH --------------------------------------------------------------------
    P("sgh", "classes", D(2026, 10, 1), D(2027, 1, 24), "zajęcia semestru zimowego", "sgh_estimate", False),
    P("sgh", "break", D(2026, 12, 23), D(2027, 1, 6), "przerwa świąteczna", "sgh_estimate", False),
    P("sgh", "exams", D(2027, 1, 25), D(2027, 2, 7), "sesja zimowa (I termin)", "sgh_sessions"),
    P("sgh", "break", D(2027, 2, 8), D(2027, 2, 12), "przerwa międzysemestralna", "sgh_estimate", False),
    P("sgh", "resit", D(2027, 2, 13), D(2027, 2, 19), "sesja zimowa (II termin)", "sgh_sessions"),
    P("sgh", "classes", D(2027, 2, 20), D(2027, 6, 13), "zajęcia semestru letniego", "sgh_estimate", False),
    P("sgh", "break", D(2027, 3, 25), D(2027, 3, 30), "przerwa wielkanocna", "sgh_estimate", False),
    P("sgh", "exams", D(2027, 6, 14), D(2027, 6, 27), "sesja letnia (I termin)", "sgh_sessions"),
    P("sgh", "break", D(2027, 6, 28), D(2027, 6, 30), "wakacje letnie", "sgh_estimate", False),
    # --- Warszawski Uniwersytet Medyczny ---------------------------------------
    P("wum", "classes", D(2026, 10, 1), D(2026, 12, 20), "zajęcia", "wum"),
    P("wum", "free_day", D(2026, 10, 5), D(2026, 10, 5), "dzień rektorski", "wum_rector_day", False),
    P("wum", "break", D(2026, 12, 21), D(2027, 1, 3), "przerwa świąteczna", "wum"),
    P("wum", "classes", D(2027, 1, 4), D(2027, 1, 31), "zajęcia", "wum"),
    P("wum", "exams", D(2027, 2, 1), D(2027, 2, 7), "sesja zimowa", "wum"),
    P("wum", "break", D(2027, 2, 8), D(2027, 2, 14), "przerwa semestralna", "wum"),
    P("wum", "resit", D(2027, 2, 15), D(2027, 2, 21), "sesja poprawkowa", "wum"),
    P("wum", "classes", D(2027, 2, 22), D(2027, 3, 24), "zajęcia", "wum"),
    P("wum", "break", D(2027, 3, 25), D(2027, 3, 31), "przerwa świąteczna", "wum"),
    P("wum", "classes", D(2027, 4, 1), D(2027, 6, 13), "zajęcia", "wum"),
    P("wum", "break", D(2027, 6, 14), D(2027, 6, 20), "przerwa na przygotowanie do sesji", "wum"),
    P("wum", "exams", D(2027, 6, 21), D(2027, 6, 30), "sesja letnia", "wum"),
]
