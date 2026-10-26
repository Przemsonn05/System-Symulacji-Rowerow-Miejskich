"""Wydarzenia w Warszawie 22.10–31.12.2026, ktore moga zmieniac popyt na rowery.

Czas lokalny (Europe/Warsaw); fetch_static przelicza go na UTC. `end` = None
oznacza nieznany koniec - przyjmowana jest typowa dlugosc dla kategorii.
`certain` = False: niepotwierdzona data/godzina albo szacowana godzina.

Stan na 25.10.2026: na PGE Narodowym w tym okresie nie ma meczow ani koncertow
(tylko targi i konferencje); mecz Polska - Szwecja (17.11) ma sie odbyc we Wroclawiu.
"""

NARODOWY = ("PGE Narodowy", 52.2395, 21.0458)
LEGIA = ("Stadion Wojska Polskiego (Legia)", 52.2206, 21.0405)
PKIN = ("Plac Defilad / PKiN", 52.2318, 21.0060)
ROND_DMOWSKIEGO = ("Rondo Dmowskiego – trasa do PGE Narodowego", 52.2306, 21.0118)
POWAZKI = ("Cmentarze Powązkowskie", 52.2556, 20.9800)

SRC_LEGIA = "https://legia.com/en/mecze"
SRC_NARODOWY = "https://www.pgenarodowy.pl/"
SRC_BIEG = "https://warszawa19115.pl/-/36.-bieg-niepodleglosci"


def E(name, venue, start, end, category, scale, source, certain=True, note=""):
    v_name, lat, lon = venue
    return {
        "name": name,
        "venue": v_name,
        "lat": lat,
        "lon": lon,
        "start_local": start,
        "end_local": end,
        "category": category,
        "scale": scale,
        "certain": certain,
        "source": source,
        "note": note,
    }


# Typowa dlugosc wydarzenia [h], gdy koniec nie jest znany.
DEFAULT_HOURS = {"match": 2, "concert": 3, "expo": 8, "conference": 9, "city": 4}

EVENTS = [
    # --- mecze Legii (stadion przy Lazienkowskiej) ------------------------------
    E("Legia – Lech Poznań (Ekstraklasa)", LEGIA, "2026-10-25 17:30", None, "match", "large", SRC_LEGIA),
    E("Legia – Raków Częstochowa (Ekstraklasa)", LEGIA, "2026-11-08 17:30", None, "match", "large", SRC_LEGIA),
    E("Legia – Wieczysta Kraków (Ekstraklasa)", LEGIA, "2026-11-28 18:00", None, "match", "large", SRC_LEGIA,
      False, "data potwierdzona, godzina nieogłoszona – przyjęto 18:00"),
    E("Legia – Pogoń Szczecin (Ekstraklasa)", LEGIA, "2026-12-12 18:00", None, "match", "large", SRC_LEGIA,
      False, "data potwierdzona, godzina nieogłoszona – przyjęto 18:00"),
    # --- PGE Narodowy (targi i konferencje) -------------------------------------
    E("Wystawa budowli z klocków LEGO", NARODOWY, "2026-10-22 10:00", "2026-10-22 18:00", "expo", "medium",
      SRC_NARODOWY, False, "wystawa wielodniowa – w kalendarium tylko data otwarcia"),
    E("Audio Video Show 2026", NARODOWY, "2026-10-25 10:00", "2026-10-25 18:00", "expo", "medium",
      SRC_NARODOWY, False, "godzina zamknięcia szacowana"),
    E("The Hack Summit 2026", NARODOWY, "2026-11-06 08:00", None, "conference", "medium", SRC_NARODOWY),
    E("ForFin 2026", NARODOWY, "2026-11-20 09:00", None, "conference", "medium", SRC_NARODOWY),
    E("Wielka Fabryka Elfów", NARODOWY, "2026-11-21 09:00", None, "expo", "medium", SRC_NARODOWY),
    E("Wielka Fabryka Elfów", NARODOWY, "2026-11-22 09:00", None, "expo", "medium", SRC_NARODOWY),
    E("Warsaw Wine Experience 2026", NARODOWY, "2026-11-22 12:00", None, "expo", "medium", SRC_NARODOWY),
    E("Warsaw Wine Experience 2026", NARODOWY, "2026-11-23 10:00", None, "expo", "medium", SRC_NARODOWY),
    E("Wielka Fabryka Elfów", NARODOWY, "2026-11-23 14:30", None, "expo", "medium", SRC_NARODOWY),
    E("Data Science Summit 2026", NARODOWY, "2026-11-27 08:00", None, "conference", "medium", SRC_NARODOWY),
    E("ELEVATE Health & Longevity Summit", NARODOWY, "2026-11-28 10:00", None, "conference", "medium", SRC_NARODOWY),
    E("ELEVATE Health & Longevity Summit", NARODOWY, "2026-11-29 10:00", None, "conference", "medium", SRC_NARODOWY),
    E("Oh My Hack 2026", NARODOWY, "2026-12-02 08:00", None, "conference", "medium", SRC_NARODOWY),
    E("WawaGra – planszówki na PGE Narodowym", NARODOWY, "2026-12-05 10:00", None, "expo", "medium", SRC_NARODOWY),
    E("WawaGra – planszówki na PGE Narodowym", NARODOWY, "2026-12-06 10:00", None, "expo", "medium", SRC_NARODOWY),
    # --- wydarzenia miejskie ------------------------------------------------------
    E("Wszystkich Świętych – ruch przy cmentarzach", POWAZKI, "2026-10-31 08:00", "2026-11-02 20:00", "city",
      "large", "https://www.um.warszawa.pl/", False,
      "coroczne; godziny i skala szacowane (ograniczenia ruchu ZDM przy cmentarzach)"),
    E("Bieg Niepodległości (10 km)", PKIN, "2026-11-11 10:00", "2026-11-11 13:30", "city", "large", SRC_BIEG,
      False, "Mila 10:00, bieg główny 11:11 (potwierdzone); lokalizacja startu i koniec szacowane"),
    E("Marsz Niepodległości", ROND_DMOWSKIEGO, "2026-11-11 14:00", "2026-11-11 19:00", "city", "large",
      "https://pl.wikipedia.org/wiki/Marsz_Niepodleg%C5%82o%C5%9Bci", False,
      "coroczny 11.11; godzina i trasa 2026 niepotwierdzone (zwykle Rondo Dmowskiego → PGE Narodowy)"),
    E("Jarmark bożonarodzeniowy przy PKiN", PKIN, "2026-11-21 12:00", "2027-01-03 21:00", "city", "medium",
      "https://pik.warszawa.pl/inne/jarmark-bozonarodzeniowy-w-warszawie/", False,
      "daty z serwisu PIK z możliwą pomyłką roku; codziennie, godziny szacowane"),
]
