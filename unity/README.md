# Wizualizacja 3D (Unity)

Interaktywna scena 3D Warszawy, która odtwarza dzień działania Veturilo na podstawie zebranych danych:

- **342 stacje jako słupki 3D**: wysokość to liczba rowerów, kolor to zapełnienie (pusta, mało, norma, pełna, ponad pojemność); pusta stacja pulsuje na czerwono,
- **każdy przejazd z danych** (ok. 7–11 tys. na dobę) jako świecący rower ze śladem, osobny kolor dla e-rowerów,
- **ciężarówki operatora** (relokacje ≥ 4 rowery) jako modele 3D z liczbą przewożonych rowerów i „falą” po dostarczeniu,
- **budynki Śródmieścia 3D** z OpenStreetMap (wysokości z OSM), drogi rowerowe, stacje metra i PKP, uczelnie,
- **pora dnia i pogoda z danych**: pozycja słońca, zmrok, zachmurzenie, mgła i deszcz (cząsteczki) według Open-Meteo,
- **panel**: zegar, pogoda, korki TomTom, KPI (rowery w drodze, puste stacje, relokacje), wykresy dnia, oś czasu, karta stacji po kliknięciu.

Scena budowana jest w całości w kodzie: nie ma prefabów ani ręcznie ustawianych obiektów. Wystarczy pusta scena i **Play**.

## Uruchomienie

**1. Dane** (w katalogu głównym repozytorium):

```bash
python -m src.data.build      # processed/
python -m src.viz.export      # unity/Assets/StreamingAssets/veturilo/
```

Eksport trwa ok. 1 min i zapisuje ok. 1 MB na dzień danych.

**Trasy po drogach.** Rowery i ciężarówki jadą po drogach tylko wtedy, gdy lokalnie są grafy dróg OSM; bez nich jadą w linii prostej. Grafy (~170 MB, poza repozytorium) buduje się raz:

```bash
python -m src.data.fetch_static --only osm --force osm   # pobiera wycinek OSM (~120 MB), kilka minut
```

Wyliczone trasy trafiają do cache `data/static/osm/viz_routes_*.parquet`, więc kolejne eksporty liczą tylko nowe pary stacji.

**2. Unity** (zalecane **Unity 6 LTS**, działa też 2022.3 LTS):

> Projekt Unity trzymaj w ścieżce **bez polskich znaków** (np. `C:\Unity\VeturiloViz`) – repozytorium leży w „…systemów…”, a Unity bywa kapryśne przy znakach spoza ASCII w ścieżce projektu.

Sposób zalecany (nowy projekt):

1. Unity Hub → **New project** → szablon **Universal 3D** (albo *3D (Built-In)*) → lokalizacja np. `C:\Unity\VeturiloViz`.
2. Skopiuj z repozytorium folder `unity/Assets/VeturiloViz/` do `Assets/` nowego projektu.
3. Wyeksportuj dane prosto do projektu:
   ```bash
   python -m src.viz.export --out C:/Unity/VeturiloViz/Assets/StreamingAssets/veturilo
   ```
4. W Unity: **File → New Scene → Basic (URP)** albo **Empty** → **Play**. Pytanie o Input System przy otwarciu: obie odpowiedzi działają.

Alternatywa: Unity Hub → **Add → Add project from disk** → folder `unity/` z repozytorium. Folder nie ma jeszcze `ProjectSettings/` ani `Packages/`, więc Hub może go nie przyjąć – wtedy użyj sposobu powyżej.

*(raz, dla zespołu)* po pierwszym udanym uruchomieniu zapisz scenę jako `Assets/Scenes/Veturilo.unity` i dodaj do repozytorium `ProjectSettings/`, `Packages/`, scenę oraz pliki `.meta` (np. do folderu `unity/`), żeby wszyscy mieli ten sam projekt.

**Domyślny dzień.** Po starcie otwiera się ostatni dzień z pełnymi danymi. Do scenariusza pokazu (piątek 23.10) przełącz dzień klawiszami `,` / `.` albo przyciskami `<` `>` na osi czasu.

Działa w Built-in Render Pipeline i w URP, ze starym Input Managerem i z nowym Input System.

## Sterowanie

| Klawisz / mysz | Akcja |
|---|---|
| PPM lub Shift + LPM | obrót kamery |
| LPM (przeciągnięcie) | przesuwanie |
| kółko | przybliżenie |
| WASD / Q E | ruch / obrót |
| klik na stację | karta stacji + kamera do stacji |
| Spacja | start / pauza |
| strzałki ← → | 15 min wstecz / naprzód |
| [ ] | wolniej / szybciej |
| , . | poprzedni / następny dzień |
| 1 2 3 4 | miasto / Śródmieście / z góry / nisko nad ulicami |
| C | kamera kinowa (do nagrania filmu) |
| H | ukryj interfejs |
| F1 | pomoc |

## Scenariusz pokazu na milestone (ok. 3 min)

1. **Start, widok miasta (1), pt 23.10, 7:00, ×300.** „To nie animacja, tylko odtworzenie rzeczywistego dnia: 342 stacje co 5 minut i 11 tys. przejazdów odtworzonych z numerów rowerów.”
2. **Poranny szczyt 7:30–9:00.** Liczba rowerów w drodze rośnie, w Śródmieściu przybywa fioletowych słupków (ponad pojemność), na obrzeżach pojawiają się pulsujące puste stacje. Wykres pustych stacji pokazuje problem, który rozwiązuje symulacja.
3. **Śródmieście (2), kliknięcie stacji przy metrze.** Karta stacji: profil dnia, otoczenie (lokale, biura, uczelnie). To cechy wejściowe modelu popytu.
4. **Ciężarówki.** Relokacje operatora z liczbą rowerów; to strategia bazowa, z którą porównujemy strategie w DES.
5. **Przewinięcie do wieczora (suwak) i niedziela 25.10.** Zmrok według położenia słońca, deszcz od ok. 18:00 i wyraźny spadek liczby przejazdów (hipoteza o wpływie pogody).
6. **Zakończenie:** ta sama wizualizacja przyjmie wynik symulacji DES (`--source sim`), więc pokażemy model obok rzeczywistości.

Na wypadek problemów z pokazem na żywo nagraj film: **Window → Package Manager → Unity Recorder**, tryb kinowy (C) i ukryty interfejs (H) albo widoczny, zależnie od ujęcia.

## Struktura

```
Assets/VeturiloViz/Scripts/
  VeturiloApp.cs     punkt wejścia: budowa sceny, czas, klawisze, wybór stacji
  DataStore.cs       wczytanie JSON, interpolacja stanu w czasie, trasy
  DataModel.cs       klasy odpowiadające plikom JSON
  CityBuilder.cs     podłoże, budynki 3D (triangulacja obrysów), drogi rowerowe, POI
  StationLayer.cs    słupki stacji, pierścienie pustych / przepełnionych
  BikeLayer.cs       rowery w drodze (pula obiektów + ślady)
  TruckLayer.cs      ciężarówki relokacji
  EnvironmentFx.cs   słońce, zmrok, mgła, deszcz z danych pogodowych
  CameraRig.cs       kamera orbitalna i tryb kinowy
  Hud.cs, Ui.cs      interfejs (uGUI budowany w kodzie)
  InputCompat.cs     obsługa starego i nowego systemu wejścia
  Mats.cs            materiały (Built-in / URP) i paleta kolorów
```

## Dane z symulacji DES

Eksporter czyta pliki w formacie `processed/` (`observed_timeseries`, `trips`, `rebalancing_observed`). Jeśli symulacja Osoby 3 zapisze wynik w tym samym formacie (np. do `processed_sim/`), wystarczy wskazać go eksporterowi i dodać `--source sim`. Panel pokaże wtedy „SYMULACJA DES”. Rozszerzenie eksportera o parametr z katalogiem wejściowym to kilka linijek.

## Problemy

- **„Nie udało się wczytać danych”:** uruchom `python -m src.viz.export` i sprawdź, czy istnieje `Assets/StreamingAssets/veturilo/index.json`.
- **Różowe obiekty:** brak shadera w buildzie. W edytorze nie występuje; przy buildzie dodaj `Standard`/`Unlit/Color` (lub shadery URP) w *Project Settings → Graphics → Always Included Shaders*.
- **Pytanie o Input System przy otwarciu:** obie odpowiedzi działają.
- **Budynki bez cieni w URP:** URP bierze zasięg cieni z ustawień renderera (domyślnie 50–150 m), a nie z kodu. Ustaw *Project Settings → Graphics → (aktywny URP Asset) → Shadows → Max Distance* na ok. 3000.
- **Kółko myszy nie przybliża:** wartości kółka są normalizowane dla starego i nowego Input System; jeśli mimo to zoom nie działa, użyj gotowych widoków `1`–`4` i zgłoś wersję pakietu Input System (*Window → Package Manager*).
- **Karta stacji pokazuje „e-rowery: brak danych”:** to poprawne dla pomiarów sprzed 23.10.2026 ok. 10:00 (wtedy jeszcze nie zbieraliśmy baterii e-rowerów).
- **Efekt świecenia (bloom):** w projekcie URP dodaj *GameObject → Volume → Global Volume*, profil z efektem *Bloom* (threshold ok. 0,9). Rowery i ślady zaczną świecić.
- **Za duże lub za małe elementy:** parametry są na komponentach w trakcie Play (`StationLayer.metersPerBike`, `BikeLayer.maxSize`, `TruckLayer.scale`, `VeturiloApp.labelScale`).
