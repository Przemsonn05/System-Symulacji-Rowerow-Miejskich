# Wizualizacja 3D (Unity)

Interaktywna scena 3D Warszawy, która **odtwarza prawdziwy dzień** systemu Veturilo z naszych danych: co 5 minut stan każdej stacji, każdy przejazd odtworzony z numerów rowerów, każda relokacja operatora, do tego pogoda, pora dnia, korki i wydarzenia. Ta sama scena przyjmie później wynik symulacji DES, więc model i rzeczywistość pokażemy w jednym widoku.

## Uruchomienie

### 1. Dane (w katalogu głównym repozytorium)

```bash
python -m src.data.build      # processed/  (ok. 1–2 min)
python -m src.viz.export      # unity/Assets/StreamingAssets/veturilo/  (ok. 1 min, ~1 MB na dzień)
python -m src.viz.export_sim results/sim/none_1/seed_1000 results/sim/operator_2/seed_1000 \
    results/sim/threshold_2/seed_1000 results/sim/threshold_4/seed_1000   # model (do 4 przebiegów jednej daty)
```

Przebieg symulacji to katalog z `kpis.json`, `station_timeseries.parquet`, `trips.parquet`, `events.parquet` (np. `python -m src.simulation run --scenario threshold --trucks 2 --out results/sim/threshold_2/seed_1000`). `export_sim` za każdym razem zastępuje listę symulacji w `index.json`, więc podaj od razu wszystkie przebiegi.

Podkład mapy (Wisła, zieleń, ulice, metro, mosty), budynki całej Warszawy i trasy po drogach rowerowych są już w repozytorium (`data/static/osm/basemap.parquet`, `buildings_warsaw.parquet`, `viz_routes_*.parquet`), więc rowery jadą po prawdziwych ulicach bez pobierania czegokolwiek. Dla nowych par stacji, których nie ma w cache, trasa jest prosta. Dokładne trasy dla nich liczy graf OSM, który trzeba zbudować raz (pobiera ~120 MB, kilka minut):

```bash
python -m src.data.fetch_static --only osm --force osm
```

### 2. Unity (Unity 6, wersja 6000.0.85f1, URP)

1. Unity Hub → **Add → Add project from disk** → folder `unity/` z repozytorium.
2. Otwórz scenę `Assets/Scenes/Veturilo.unity` (jeśli jej nie ma: menu **Veturilo → Utwórz scenę**).
3. **Play**. Cała scena buduje się z kodu; po starcie otwiera się ostatni pełny dzień roboczy, godzina 7:00.

**Samodzielna aplikacja (do prezentacji bez edytora):** menu **Veturilo → Zbuduj aplikację (Windows)**. Powstaje `unity/Build/Veturilo.exe`, a dane są w środku. Z wiersza poleceń:

```bash
"D:\Unity\Editors\6000.0.85f1\Editor\Unity.exe" -batchmode -quit -projectPath unity -executeMethod Veturilo.Viz.Editor.VeturiloBuild.BatchBuild
```

**Zrzuty do raportu:** `F12` w trakcie działania albo cała seria naraz:

```bash
unity\Build\Veturilo.exe -screen-fullscreen 0 -vtShots C:\zrzuty
```

Seria to 16 zrzutów (m.in. Wisła w dzień z odbiciami i deszczowy wieczór 25.10 z mokrymi ulicami): miasto rano, Śródmieście w szczycie, bilans z łukami OD, mapa H2, utracony popyt, ulice wieczorem, noc nad Wisłą, ślady całego dnia, mieszkańcy, karta stacji, śledzenie roweru, porównanie dwóch dni i pokaz. Aplikacja sama się zamyka.

## Co widać

| Element | Co pokazuje | Dane |
|---|---|---|
| **Słupki stacji** | widok *Zapełnienie*: wysokość = rowery, kolor = zapełnienie; pusta stacja pulsuje na czerwono | `observed_timeseries` (co 5 min) |
| **Świecące punkty ze śladem** | każdy przejazd: żółty rower, niebieski e-rower, rozbłysk przy oddaniu; jadą po drogach rowerowych | `trips` + graf OSM |
| **Ciężarówki z „kogutem”** | relokacje operatora (≥ 4 rowery razem), etykieta `+n` rowerów, fala po dostarczeniu | `rebalancing_observed` |
| **Białe punkty** | rowery zostawione poza stacjami | `data/loose` |
| **Łuki OD** (F) | najczęstsze trasy ostatniej godziny; grubość = liczba przejazdów, kolor żółty → niebieski = kierunek | `trips` |
| **Wisła, zieleń, lasy, ulice, tory, granica miasta** | podkład z OSM; wieczorem ulice świecą, a wzdłuż głównych ulic zapalają się latarnie | `basemap.parquet` |
| **Metro M1 / M2, mosty** | linie w kolorach metra (M1 niebieska, M2 czerwona), mosty jako przęsła nad Wisłą | `basemap.parquet` |
| **Drzewa** | ok. 90 tys. drzew w parkach, lasach i na cmentarzach, w jesiennych kolorach (dane są z października i listopada) | `basemap.parquet` |
| **Budynki całej Warszawy 3D** | ok. 180 tys. budynków z OSM (wysokość z tagów, kondygnacji albo typu budynku), elewacje z oknami; po zmroku okna się zapalają | `buildings_warsaw.parquet` |
| **Ślady dnia** (G) | ślady wszystkich przejazdów narastające w ciągu dnia; jasne pasy = główne korytarze rowerowe | `trips` |
| **Utracony popyt** (U) | heksagony rosnące tam, gdzie klienci przychodzą do pustej stacji (szacunek, liczba osób od północy) | stan stacji + popyt z `station_hourly` |
| **Korki** (K) | znaczniki na 10 arteriach TomTom z % spowolnienia (zielony → czerwony) i utrudnienia (wypadki, korki, zamknięcia, roboty) | `data/traffic_flow`, `data/incidents` |
| **Wydarzenia** | słup światła nad obiektem (stadion, Narodowy) od 1,5 h przed startem | `events.csv` |
| **Mieszkańcy** (P) | heksagony gęstości zaludnienia | `population_h3` |
| **Grafika (URP)** | bloom (neonowe światła rowerów, okien i latarni), tonemapping ACES, SSAO (głębia między budynkami), wygładzanie krawędzi, winieta; nocą mocniejsza poświata | `Assets/VeturiloViz/Settings/VeturiloURP.asset` |
| **Wisła z odbiciem** | woda odbija miasto, światła i niebo (osobna kamera lustrzana), fale, odblask słońca | shader `Veturilo/Water` |
| **Cienie chmur** | chmury przesuwają się z wiatrem po mieście; zakrywają tyle nieba, ile wynosi zachmurzenie z danych | Open-Meteo |
| **Mokre ulice** | w deszczu i do ok. 1,5 h po nim nawierzchnia i dachy ciemnieją i błyszczą, światła się w nich odbijają | opad z Open-Meteo |
| **Niebo i pogoda** | położenie słońca, świt i zmierzch, gwiazdy, chmury, mgła, deszcz z wiatrem | `context_hourly` (Open-Meteo) |

**Trzy widoki stacji (V):**
- **Zapełnienie:** stan teraz.
- **Bilans 1 h:** zwroty minus wypożyczenia w ostatniej godzinie. Czerwone stacje tracą rowery, niebieskie zyskują. Widać poranny odpływ z osiedli do centrum.
- **H2: pustki:** jak często stacja była pusta w całym okresie zbierania. Czerwone to 10% najczęściej pustych. Wprost ilustruje hipotezę H2.

**Śledzenie (klik na rower lub ciężarówkę):** kamera jedzie za rowerem, a u góry widać numer roweru, skąd, dokąd, dystans, czas przejazdu i ile zostało do celu. Esc kończy śledzenie.

**Dane | model (X):** ekran dzieli się na pół. Po lewej prawdziwy dzień, po prawej symulacja tego samego dnia (najpierw odtworzenie operatora), o tej samej godzinie. Gdy dla dnia nie ma symulacji – inny dzień (dla roboczego ostatni wolny). Nagłówki nad panelami: rowery w drodze, przejazdy, puste stacje i **utraceni klienci** (w modelu dokładnie, w danych szacunek). Prawy widok zmieniasz `Shift + ,` `Shift + .` albo przyciskami „prawy <  >” (kolejno dni i przebiegi modelu).

**Strategie (Z):** do 4 przebiegów symulacji tej samej daty w ćwiartkach ekranu (np. bez relokacji, operator, progowa 2 i 4 ciężarówki), z licznikiem utraconych klientów i kilometrami ciężarówek nad każdą. **N** przełącza główny widok między danymi a kolejnymi przebiegami modelu tej daty.

**Agenci modelu (J):** ludziki przy stacjach – czekają przy pustej stacji, idą do sąsiedniej (zielona linia), odchodzą z ✕. Kolor = typ klienta (dojeżdżający, student, rekreacyjny, e-rowerzysta), gdy symulacja go zapisuje. **Dyspozytor (O):** pomarańczowy łuk od ciężarówki do stacji, która dostała rowery w zadaniu, z numerem ciężarówki i liczbą rowerów; czerwony sygnał nad stacją, jeśli model zapisuje `signal_on`.

**Fale pustek (B):** stacja pustoszeje, a w ciągu 20 min pustoszeje stacja do 800 m od niej – różowe pierścienie i łuki „kto kogo zaraził”, licznik „fala pustek · 5/9”. Działa dla danych i modelu (te same funkcje co `python -m src.metrics`, siatka 5 min). **Ciśnienie (Y):** mapa ciepła na ziemi – czerwony = mniej rowerów niż zwykle na tej stacji (pusta = najmocniej), niebieski = więcej; rano widać odpływ z osiedli do centrum.

**Pasek „na żywo”** (u góry na środku): ostatnie zdarzenia – stacja pusta, ciężarówka zabrała / przywiozła rowery, fala pustek, klienci odchodzą z niczym (model). **Trasy dojazdowe** (`processed/commute_pairs.parquet`) mają różowe rowery.


**Utracony popyt – jak liczony:** dla każdej stacji, godziny i typu dnia szacujemy popyt z godzin, w których stacja miała rowery (wypożyczenia / godziny dostępności; przy małej liczbie obserwacji ściągnięty do profilu całego systemu). Każde 5 minut pustej stacji to popyt tej godziny / 12 klientów, którzy odeszli z niczym. To szacunek – dokładniej policzy go model popytu.

**Panele:**
- zegar, pogoda (temperatura, odczuwalna, wiatr, opad), jakość powietrza, korki, wydarzenia,
- KPI: rowery w drodze, przejazdy, puste i przepełnione stacje, relokacje, rowery poza obiegiem, szacowany utracony popyt,
- wykresy dnia: przejazdy na godzinę i puste stacje,
- lista stacji, które są **puste najdłużej**; kliknięcie przenosi kamerę do stacji,
- **karta stacji** po kliknięciu: stan, ruch w ostatniej godzinie, ranking pustek, otoczenie (lokale, biura, uczelnie, mieszkańcy, komunikacja), wykres dnia, wypożyczenia i zwroty co godzinę.

## Sterowanie

| Klawisz / mysz | Akcja |
|---|---|
| PPM lub Shift + LPM | obrót kamery |
| LPM (przeciągnięcie) / kółko | przesuwanie / przybliżenie |
| WASD, Q E | ruch, obrót |
| klik na stację | karta stacji + kamera do stacji |
| Spacja | start / pauza |
| ← → | 15 min wstecz / naprzód |
| [ ] | wolniej / szybciej |
| , . | poprzedni / następny dzień |
| 1 2 3 4 5 | miasto / Śródmieście / z góry / nisko nad ulicami / Wisła i mosty |
| V | widok stacji: zapełnienie → bilans → H2 |
| klik na rower / ciężarówkę | kamera jedzie za nim (Esc – koniec) |
| X | dane \| model tego dnia (Shift + , . – zmiana prawego widoku: dni i przebiegi modelu) |
| Z | do 4 strategii relokacji obok siebie |
| N | główny widok: dane / kolejne przebiegi modelu |
| J / O / B / Y | agenci modelu / dyspozytor / fale pustek / ciśnienie |
| G / U | ślady całego dnia / utracony popyt |
| **T** | **pokaz z komentarzem** (ok. 2 min, cały dzień) |
| F / K / P / M | łuki OD / korki / mieszkańcy / podkład mapy |
| C | kamera kinowa |
| H | ukryj panele |
| F12 | zrzut ekranu (folder `Screenshots`) |
| F1 | pomoc |

## Scenariusz prezentacji (ok. 3 min)

Najprościej: **T** uruchamia gotowy pokaz z napisami. Kamera, widoki i komentarz zmieniają się same:

1. **5:30, całe miasto.** „To nie animacja, tylko prawdziwy dzień – N przejazdów odtworzonych z numerów rowerów.”
2. **7:00, szczyt poranny.** Rowery jadą z osiedli do centrum.
3. **8:00, Bilans 1 h + łuki OD.** Czerwone stacje tracą rowery, łuki pokazują najczęstsze trasy.
4. **9:30, Śródmieście.** Centrum przepełnione (fiolet), obrzeża pustoszeją (czerwone pulsowanie).
5. **11:00, ciężarówki.** Relokacje operatora to strategia bazowa dla symulacji.
6. **13:00, H2.** Pustki skupione na niewielu stacjach; liczby z danych w napisie.
7. **14:00, utracony popyt.** Heksagony rosną tam, gdzie klienci odchodzą od pustych stacji.
8. **15:00, kontekst.** Korki, pogoda, wydarzenia, czyli zmienne modelu popytu.
9. **16:00, popołudniowy szczyt** (kamera kinowa) → **17:30 zmierzch** (okna i latarnie) → **20:00 ślady całego dnia** (korytarze rowerowe) → zakończenie.

Ręcznie: dzień zmieniasz klawiszami `,` `.`, godzinę suwakiem, widok klawiszem `V`. Na wypadek problemów z pokazem na żywo nagraj film: **Window → Package Manager → Unity Recorder**, kamera kinowa (C), panele ukryte (H).

## Struktura

```
Assets/Scenes/Veturilo.unity            pusta scena (kamera + światło) - resztę tworzy kod
Assets/VeturiloViz/Scripts/
  VeturiloApp.cs     punkt wejścia: budowa sceny, czas, klawisze, warstwy, ujęcia, śledzenie, porównania (2-4 panele), zrzuty
  DataStore.cs       wczytanie JSON, stan w czasie t, bilans stacji, H2 (Gini, udziały), trasy
  DataModel.cs       klasy odpowiadające plikom JSON
  CityBuilder.cs     podłoże, Wisła, zieleń, ulice, mosty, metro, granica, budynki całego miasta z oknami, drogi rowerowe, POI
  CityExtras.cs      drzewa (GPU instancing) i latarnie
  AnalysisLayers.cs  ślady całego dnia, utracony popyt (heksagony)
  AgentLayers.cs     agenci modelu i dyspozytor, fale pustek, mapa ciśnienia
  StationLayer.cs    słupki stacji w trzech widokach, pierścienie, poświata
  BikeLayer.cs       rowery w drodze (ślady, poświata, rozbłyski), rowery poza stacjami
  TruckLayer.cs      ciężarówki relokacji
  FlowLayer.cs       łuki OD
  ContextLayer.cs    wydarzenia, korki TomTom, utrudnienia
  EnvironmentFx.cs   słońce, niebo, gwiazdy, cienie chmur, mgła, deszcz, mokre ulice; Night01 dla świateł miasta
  RenderFx.cs        post-processing URP (bloom, ACES, kolor) i odbicie w wodzie
  Tour.cs            pokaz z komentarzem (T)
  Fx.cs              poświata z cząsteczek, opisy 3D
  CameraRig.cs       kamera orbitalna, przeloty, tryb kinowy
  Hud.cs, Ui.cs      interfejs (uGUI budowany w kodzie), wykresy
  InputCompat.cs     stary Input Manager i nowy Input System
  Mats.cs            materiały, tekstury elewacji i poświaty, paleta kolorów
Assets/VeturiloViz/Shaders/DayTrails.shader  shader śladów całego dnia
Assets/VeturiloViz/Shaders/Water.shader      woda z odbiciem i falami (URP)
Assets/VeturiloViz/Settings/                 potok URP i renderer z SSAO
Assets/VeturiloViz/Editor/VeturiloBuild.cs   menu Veturilo: scena, szablony materiałów, build
Assets/VeturiloViz/Resources/VeturiloMaterials/   szablony materiałów (shadery w zbudowanej aplikacji)
```

## Dane z symulacji DES

`python -m src.viz.export_sim` zapisuje dla każdego przebiegu `sim_<strategia>_<ciężarówki>_s<ziarno>_<data>.json` w tym samym formacie co dzień rzeczywisty, plus: agentów (rezygnacje, przejścia, czekanie, zadania dyspozytora, sygnały stacji), fale pustek, dokładny utracony popyt i własne trasy (`sim_routes.json`, `sim_truck_routes.json` – pary stacji, których nie było w danych). Pogoda, korki i wydarzenia są brane z dnia rzeczywistego tej samej daty. Schemat zdarzeń, które wizualizacja rozumie (także przyszłe: `user_wait_*`, `signal_*`, `task_awarded`, kolumna `pressure`): [`docs/kontrakty.md`](../docs/kontrakty.md).

Zrzuty samych widoków modelu (szybki test po zmianach): `Veturilo.exe -screen-fullscreen 0 -vtShots C:\zrzuty -vtShotsSet sim`.

## Problemy

- **„Nie udało się wczytać danych”:** uruchom `python -m src.viz.export` i sprawdź, czy istnieje `Assets/StreamingAssets/veturilo/index.json`.
- **Rowery jadą w linii prostej:** brak tras w cache dla tych par stacji. Zbuduj graf (`fetch_static --only osm --force osm`) i powtórz eksport.
- **Brak Wisły i ulic:** brak `data/static/osm/basemap.parquet` albo stary eksport. Powtórz `python -m src.viz.export`.
- **Różowe obiekty:** projekt używa URP. Jeśli Unity nie przełączyło się samo, użyj menu **Veturilo → Ustaw URP (bloom, cienie, SSAO)**. W zbudowanej aplikacji: **Veturilo → Odśwież szablony materiałów** i zbuduj ponownie.
- **Okna nie świecą nocą w zbudowanej aplikacji:** szablon `Resources/VeturiloMaterials/Facade.mat` musi mieć słowo kluczowe `_EMISSION` (od niego zależy, czy wariant shadera trafi do buildu).
- **Pytanie o Input System przy otwarciu:** obie odpowiedzi działają.
- **„e-rowery: brak danych” w karcie stacji:** to poprawne dla pomiarów sprzed 23.10.2026 ok. 10:00.
- **Wolne działanie na słabszym komputerze:** najpierw wyłącz warstwę **Efekty** (bloom, SSAO, odbicia w wodzie), potem Budynki i Mapa (z drzewami) albo obniż *Project Settings → Quality*. Drzewa są rysowane tylko z bliska.
- **Za duże lub za małe elementy:** parametry są na komponentach w trakcie Play (`StationLayer.metersPerBike`, `BikeLayer.maxSize`, `TruckLayer.scale`, `VeturiloApp.labelScale`).
