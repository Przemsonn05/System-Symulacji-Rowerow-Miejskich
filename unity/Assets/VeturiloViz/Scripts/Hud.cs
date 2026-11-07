// Panel informacyjny: zegar, pogoda, KPI, wykresy dnia, widok stacji z legenda, warstwy, karta stacji,
// lista stacji pustych najdluzej, os czasu, napisy pokazu, pomoc, pasek zdarzen "na zywo",
// naglowki paneli porownania (2-4 widoki: dane | model, strategie).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Veturilo.Viz
{
    public class Hud
    {
        readonly VeturiloApp app;
        Canvas canvas;
        Text title, dateLine, clock, tempBig, weatherDesc, weather2, weather3, eventsLine;
        Text dayLabel, speedLabel, tooltip, help, message, caption, modeDesc, emptyTitle;
        Text kInUse, kTrips, kEmpty, kOver, kTrucks, kFleet, kLost, kLostLabel, kTrucksLabel;
        RectTransform followPanel, compareClock, tickerPanel;
        readonly RectTransform[] cmpPanels = new RectTransform[4];
        readonly Text[] cmpTexts = new Text[4];
        readonly RectTransform[] dividers = new RectTransform[3];
        Text followText, cmpClock, tickerText;
        readonly List<DataStore.TickerItem> tickerItems = new List<DataStore.TickerItem>();
        readonly List<GameObject> mainPanels = new List<GameObject>();
        BarChart tripsChart, emptyChart, stationChart, flowChart, timelineChart;
        Slider slider;
        Button play, tourButton, compareButton, strategiesButton, modelButton;
        readonly List<(Button b, float speed)> speedButtons = new List<(Button, float)>();
        readonly Dictionary<string, Button> layerButtons = new Dictionary<string, Button>();
        readonly Dictionary<ViewMode, Button> modeButtons = new Dictionary<ViewMode, Button>();
        readonly Dictionary<ViewMode, GameObject> legends = new Dictionary<ViewMode, GameObject>();
        RectTransform stationPanel, emptyPanel, helpPanel, tooltipRect, captionPanel;
        Text stName, stNow, stInfo;
        readonly Button[] emptyRows = new Button[6];
        readonly StationView[] emptyRowStation = new StationView[6];
        bool sliderLock;
        StationView chartFor;
        float captionUntil, nextListUpdate;

        public bool Visible { get; private set; } = true;

        public Hud(VeturiloApp app) { this.app = app; }

        public void Build()
        {
            canvas = Ui.CreateCanvas(app.transform);
            var root = canvas.transform;

            // ------------------------------------------------ lewy gorny: zegar, pogoda, kontekst
            var top = Ui.Panel("Info", root, new Vector2(0, 1), new Vector2(20, -20), new Vector2(450, 262));
            title = Ui.Label(top, "VETURILO · Warszawa", 16, new Vector2(18, -14), new Vector2(420, 22), color: Ui.Accent, style: FontStyle.Bold);
            dateLine = Ui.Label(top, "", 16, new Vector2(18, -40), new Vector2(420, 22));
            clock = Ui.Label(top, "--:--", 62, new Vector2(12, -64), new Vector2(210, 74), style: FontStyle.Bold);
            tempBig = Ui.Label(top, "", 34, new Vector2(232, -70), new Vector2(200, 40), style: FontStyle.Bold);
            weatherDesc = Ui.Label(top, "", 16, new Vector2(234, -110), new Vector2(210, 22), color: Ui.TextDim);
            weather2 = Ui.Label(top, "", 14, new Vector2(18, -150), new Vector2(424, 20), color: Ui.TextDim);
            weather3 = Ui.Label(top, "", 14, new Vector2(18, -172), new Vector2(424, 20), color: Ui.TextDim);
            eventsLine = Ui.Label(top, "", 15, new Vector2(18, -200), new Vector2(420, 44), color: Mats.Event);

            // ------------------------------------------------ lewy: KPI i wykresy
            var kpi = Ui.Panel("KPI", root, new Vector2(0, 1), new Vector2(20, -294), new Vector2(450, 576));
            int y = -16;
            kInUse = KpiRow(kpi, "Rowery w drodze", ref y, Mats.Bike);
            kTrips = KpiRow(kpi, "Przejazdy od północy", ref y, Ui.TextMain);
            kEmpty = KpiRow(kpi, "Puste stacje", ref y, Mats.Empty);
            kOver = KpiRow(kpi, "Stacje ponad pojemność", ref y, Mats.Overfull);
            kTrucks = KpiRow(kpi, "Relokacje operatora", ref y, Mats.Truck, out kTrucksLabel);
            kFleet = KpiRow(kpi, "Na stacjach / poza obiegiem", ref y, Mats.Ok);
            kLost = KpiRow(kpi, "Utracony popyt od północy (szac.)", ref y, LostDemandLayer.LostColor(12f), out kLostLabel);
            Ui.Label(kpi, "Przejazdy na godzinę", 14, new Vector2(18, y - 6), new Vector2(420, 20), color: Ui.TextDim);
            tripsChart = new BarChart(kpi, new Vector2(18, y - 28), new Vector2(414, 92), 25, new Color(1f, 0.8f, 0.2f, 0.6f), Color.white);
            Ui.Label(kpi, "Puste stacje w ciągu dnia (średnio co 30 min)", 14, new Vector2(18, y - 130), new Vector2(420, 20), color: Ui.TextDim);
            emptyChart = new BarChart(kpi, new Vector2(18, y - 152), new Vector2(414, 70), 50, new Color(0.95f, 0.2f, 0.25f, 0.55f), Color.white);
            for (int h = 0; h <= 24; h += 6)
            {
                var tick = Ui.Label(kpi, h.ToString("00"), 11, new Vector2(18 + 414f * h / 25f - 6, y - 224), new Vector2(30, 14), color: Ui.TextDim);
                tick.raycastTarget = false;
            }

            // ------------------------------------------------ prawy gorny: widok stacji, legenda, warstwy
            var view = Ui.Panel("View", root, new Vector2(1, 1), new Vector2(-20, -20), new Vector2(390, 588));
            Ui.Label(view, "Widok stacji  (V)", 15, new Vector2(16, -14), new Vector2(300, 22), color: Ui.TextDim);
            int mx = 16;
            foreach (var (mode, label) in new[] { (ViewMode.Fill, "Zapełnienie"), (ViewMode.Balance, "Bilans 1 h"), (ViewMode.Problem, "H2: pustki") })
            {
                var m = mode;
                modeButtons[m] = Ui.Button(view, label, new Vector2(mx, -40), new Vector2(116, 32), () => app.SetMode(m), 15);
                mx += 122;
            }
            modeDesc = Ui.Label(view, "", 14, new Vector2(16, -80), new Vector2(360, 54), color: Ui.TextDim);

            legends[ViewMode.Fill] = Legend(view, -136, new[]
            {
                (Mats.Empty, "pusta – pulsuje (klient odchodzi)"), (Mats.Low, "mało rowerów (< 25% stojaków)"),
                (Mats.Ok, "w normie"), (Mats.Full, "pełna (do 150% stojaków – normalne)"), (Mats.Overfull, "mocno przepełniona (> 150%)"), (Mats.NoData, "brak danych"),
            });
            legends[ViewMode.Balance] = Legend(view, -136, new[]
            {
                (Mats.Losing, "traci rowery (więcej wypożyczeń)"), (Mats.Gaining, "zyskuje rowery (więcej zwrotów)"),
                (Mats.Neutral, "bez zmian"), (Mats.Empty, "pusta teraz (pierścień)"),
            });
            legends[ViewMode.Problem] = Legend(view, -136, new[]
            {
                (Mats.Empty, "10% stacji najczęściej pustych"), (Mats.Low, "kolejne 10%"),
                (new Color(0.75f, 0.72f, 0.4f), "pozostałe"), (new Color(0.28f, 0.42f, 0.34f), "nigdy nie była pusta"),
            });
            int ly = -136 - 6 * 22 - 8;
            Ui.Label(view, "W ruchu", 14, new Vector2(16, ly), new Vector2(300, 20), color: Ui.TextDim);
            ly -= 22;
            // dwie kolumny, zeby zmiescic agentow i analizy bez powiekszania panelu
            var moving = new (Color c, string label)[]
            {
                (Mats.Bike, "rower w drodze"), (Mats.EBike, "e-rower w drodze"),
                (Mats.Commute, "trasa dojazdowa"), (Mats.Truck, "ciężarówka (+ rowery)"),
                (new Color(0.95f, 0.95f, 1f), "klient modelu (J)"), (Mats.Leaving, "odchodzi z niczym ✕"),
                (Mats.Cascade, "fala pustek (B)"), (Mats.Dispatch, "zadanie dyspozytora (O)"),
            };
            for (int i = 0; i < moving.Length; i += 2)
            {
                LegendCell(view, moving[i].c, moving[i].label, 16, ly);
                LegendCell(view, moving[i + 1].c, moving[i + 1].label, 200, ly);
                ly -= 22;
            }

            Ui.Label(view, "Warstwy", 14, new Vector2(16, ly - 6), new Vector2(300, 20), color: Ui.TextDim);
            int bx = 16, by = ly - 30;
            foreach (var name in VeturiloApp.LayerNames)
            {
                string n = name;
                var b = Ui.Button(view, n, new Vector2(bx, by), new Vector2(86, 28), () => app.ToggleLayer(n), 12);
                layerButtons[n] = b;
                bx += 90;
                if (bx > 300) { bx = 16; by -= 32; }
            }

            // ------------------------------------------------ prawy: karta stacji albo lista pustych
            stationPanel = Ui.Panel("Station", root, new Vector2(1, 1), new Vector2(-20, -622), new Vector2(390, 344));
            stName = Ui.Label(stationPanel, "", 17, new Vector2(16, -12), new Vector2(360, 24), style: FontStyle.Bold);
            stNow = Ui.Label(stationPanel, "", 24, new Vector2(16, -38), new Vector2(360, 32), style: FontStyle.Bold);
            stInfo = Ui.Label(stationPanel, "", 13, new Vector2(16, -74), new Vector2(362, 120), color: Ui.TextDim);
            Ui.Label(stationPanel, "Rowery na stacji w ciągu dnia", 12, new Vector2(16, -204), new Vector2(360, 16), color: Ui.TextDim);
            stationChart = new BarChart(stationPanel, new Vector2(16, -222), new Vector2(358, 48), 96, new Color(0.25f, 0.85f, 0.45f, 0.6f), Color.white);
            Ui.Label(stationPanel, "Wypożyczenia (żółte) i zwroty (niebieskie) co godzinę", 12, new Vector2(16, -278), new Vector2(360, 16), color: Ui.TextDim);
            flowChart = new BarChart(stationPanel, new Vector2(16, -296), new Vector2(358, 44), 48, Mats.Bike, Color.white);
            flowChart.SetColors(i => i % 2 == 0 ? new Color(1f, 0.8f, 0.2f, 0.75f) : new Color(0.3f, 0.75f, 1f, 0.75f));
            stationPanel.gameObject.SetActive(false);

            emptyPanel = Ui.Panel("EmptyList", root, new Vector2(1, 1), new Vector2(-20, -622), new Vector2(390, 250));
            emptyTitle = Ui.Label(emptyPanel, "Najdłużej puste teraz", 15, new Vector2(16, -12), new Vector2(360, 22), color: Ui.TextDim);
            for (int i = 0; i < emptyRows.Length; i++)
            {
                int k = i;
                emptyRows[i] = Ui.Button(emptyPanel, "", new Vector2(12, -40 - i * 34), new Vector2(366, 30), () => OnEmptyRow(k), 14, TextAnchor.MiddleLeft);
            }

            // ------------------------------------------------ dol: os czasu
            var bar = Ui.Rect("Timeline", root, new Vector2(0, 0), new Vector2(1, 0), new Vector2(0.5f, 0), new Vector2(0, 16), new Vector2(-40, 98));
            var barImg = bar.gameObject.AddComponent<Image>();
            barImg.color = Ui.PanelBg;
            Ui.Button(bar, "<", new Vector2(14, -12), new Vector2(40, 32), () => app.ChangeDay(-1));
            dayLabel = Ui.Label(bar, "", 17, new Vector2(56, -12), new Vector2(150, 32), TextAnchor.MiddleCenter);
            Ui.Button(bar, ">", new Vector2(208, -12), new Vector2(40, 32), () => app.ChangeDay(+1));
            play = Ui.Button(bar, "Pauza", new Vector2(264, -12), new Vector2(80, 32), () => app.TogglePlay(), 17);
            int sx = 356;
            foreach (var sp in new[] { 60f, 300f, 900f, 1800f, 3600f })
            {
                float s = sp;
                var b = Ui.Button(bar, "×" + s, new Vector2(sx, -12), new Vector2(66, 32), () => app.SetSpeed(s), 14);
                speedButtons.Add((b, s));
                sx += 70;
            }
            speedLabel = Ui.Label(bar, "", 14, new Vector2(sx + 6, -18), new Vector2(160, 24), color: Ui.TextDim);
            tourButton = Ui.Button(bar, "Pokaz (T)", new Vector2(sx + 170, -12), new Vector2(120, 32), () => app.ToggleTour(), 15);
            Ui.Button(bar, "Zrzut (F12)", new Vector2(sx + 296, -12), new Vector2(120, 32), () => app.Screenshot(), 15);
            compareButton = Ui.Button(bar, "Porównaj (X)", new Vector2(sx + 422, -12), new Vector2(130, 32), () => app.ToggleCompare(), 15);
            Ui.Button(bar, "prawy <", new Vector2(sx + 558, -12), new Vector2(84, 32), () => app.ChangeDayB(-1), 14);
            Ui.Button(bar, ">", new Vector2(sx + 646, -12), new Vector2(36, 32), () => app.ChangeDayB(+1), 14);
            modelButton = Ui.Button(bar, "Model (N)", new Vector2(sx + 694, -12), new Vector2(110, 32), () => app.ToggleModel(), 15);
            strategiesButton = Ui.Button(bar, "Strategie (Z)", new Vector2(sx + 810, -12), new Vector2(130, 32), () => app.ToggleStrategies(), 15);

            timelineChart = new BarChart(bar, new Vector2(22, -50), new Vector2(1844, 40), 25, new Color(1f, 0.8f, 0.2f, 0.18f), new Color(1f, 0.8f, 0.2f, 0.45f), false);
            var tcr = timelineChart.Area;
            tcr.anchorMin = new Vector2(0, 1); tcr.anchorMax = new Vector2(1, 1); tcr.sizeDelta = new Vector2(-44, 40);
            slider = Ui.Slider(bar, new Vector2(14, -54), new Vector2(1820, 30), v => { if (!sliderLock) app.Seek(v); });
            var sr = slider.GetComponent<RectTransform>();
            sr.anchorMin = new Vector2(0, 1); sr.anchorMax = new Vector2(1, 1); sr.sizeDelta = new Vector2(-28, 30);
            for (int h = 0; h <= 24; h += 3)
            {
                var tick = Ui.Label(bar, h.ToString("00") + ":00", 12, Vector2.zero, new Vector2(60, 16), TextAnchor.UpperCenter, Ui.TextDim);
                var tr = tick.rectTransform;
                tr.anchorMin = tr.anchorMax = new Vector2(0.0075f + 0.985f * h / 24f, 0);
                tr.pivot = new Vector2(0.5f, 0);
                tr.anchoredPosition = new Vector2(0, 2);
            }

            var hint = Ui.Label(root, "F1 pomoc · T pokaz · X dane | model · Z strategie · N model · V widok · klik na rower – śledź", 14, Vector2.zero, new Vector2(700, 20), TextAnchor.LowerRight, Ui.TextDim);
            hint.rectTransform.anchorMin = hint.rectTransform.anchorMax = hint.rectTransform.pivot = new Vector2(1, 0);
            hint.rectTransform.anchoredPosition = new Vector2(-24, 124);
            hint.gameObject.name = "Hint";

            // sledzony rower / ciezarowka (u gory na srodku)
            followPanel = Ui.Panel("Follow", root, new Vector2(0.5f, 1), new Vector2(0, -20), new Vector2(640, 92));
            followPanel.pivot = new Vector2(0.5f, 1);
            followText = Ui.Label(followPanel, "", 18, new Vector2(20, -12), new Vector2(600, 74), TextAnchor.UpperCenter);
            followPanel.gameObject.SetActive(false);

            // pasek zdarzen "na zywo" (u gory na srodku)
            tickerPanel = Ui.Panel("Ticker", root, new Vector2(0.5f, 1), new Vector2(0, -20), new Vector2(640, 118), new Color(0.03f, 0.04f, 0.06f, 0.78f));
            tickerPanel.pivot = new Vector2(0.5f, 1);
            Ui.Label(tickerPanel, "NA ŻYWO", 12, new Vector2(16, -10), new Vector2(120, 16), color: Ui.Accent, style: FontStyle.Bold);
            tickerText = Ui.Label(tickerPanel, "", 15, new Vector2(16, -28), new Vector2(608, 88));

            // porownanie: naglowki nad kazdym panelem, zegar na srodku, linie podzialu
            for (int k = 0; k < dividers.Length; k++)
            {
                dividers[k] = Ui.Rect("Divider", root, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
                var di = dividers[k].gameObject.AddComponent<Image>();
                di.color = new Color(Ui.Accent.r, Ui.Accent.g, Ui.Accent.b, 0.9f);
                di.raycastTarget = false;
            }
            for (int k = 0; k < cmpPanels.Length; k++)
            {
                cmpPanels[k] = Ui.Panel("Compare" + k, root, new Vector2(0, 1), Vector2.zero, new Vector2(470, 96));
                cmpPanels[k].pivot = new Vector2(0, 1);
                cmpTexts[k] = Ui.Label(cmpPanels[k], "", 15, new Vector2(14, -10), new Vector2(446, 82));
            }
            compareClock = Ui.Panel("CompareClock", root, new Vector2(0.5f, 1), new Vector2(0, -20), new Vector2(190, 74));
            compareClock.pivot = new Vector2(0.5f, 1);
            cmpClock = Ui.Label(compareClock, "", 48, new Vector2(0, -8), new Vector2(190, 60), TextAnchor.UpperCenter, style: FontStyle.Bold);
            foreach (var r in dividers) r.gameObject.SetActive(false);
            foreach (var r in cmpPanels) r.gameObject.SetActive(false);
            compareClock.gameObject.SetActive(false);
            foreach (var name in new[] { "Info", "KPI", "View" }) mainPanels.Add(root.Find(name).gameObject);

            // napisy pokazu (nad osia czasu, na srodku)
            captionPanel = Ui.Panel("Caption", root, new Vector2(0.5f, 0), new Vector2(0, 150), new Vector2(980, 86), new Color(0.02f, 0.03f, 0.05f, 0.82f));
            captionPanel.pivot = new Vector2(0.5f, 0);
            caption = Ui.Label(captionPanel, "", 24, new Vector2(24, -14), new Vector2(932, 64), TextAnchor.MiddleCenter);
            captionPanel.gameObject.SetActive(false);

            // tooltip stacji
            tooltipRect = Ui.Panel("Tooltip", root, new Vector2(0, 0), Vector2.zero, new Vector2(360, 34), new Color(0, 0, 0, 0.82f), false);
            tooltipRect.pivot = new Vector2(0, 0);
            tooltip = Ui.Label(tooltipRect, "", 15, new Vector2(10, -7), new Vector2(340, 24));
            tooltipRect.gameObject.SetActive(false);

            // pomoc
            helpPanel = Ui.Panel("Help", root, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(780, 680), new Color(0.03f, 0.04f, 0.06f, 0.96f));
            helpPanel.pivot = new Vector2(0.5f, 0.5f);
            help = Ui.Label(helpPanel, HelpText, 16, new Vector2(30, -24), new Vector2(720, 640));
            helpPanel.gameObject.SetActive(false);

            message = Ui.Label(root, "", 22, Vector2.zero, new Vector2(1100, 300), TextAnchor.MiddleCenter, Ui.TextMain);
            message.rectTransform.anchorMin = message.rectTransform.anchorMax = message.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            message.rectTransform.anchoredPosition = Vector2.zero;
            message.gameObject.name = "Message";
        }

        const string HelpText =
            "<b>Co widać</b>\n" +
            "Odtworzenie prawdziwego dnia systemu Veturilo z naszych danych: stan 340+ stacji co 5 min, " +
            "każdy przejazd odtworzony z numerów rowerów (czas ±5 min), relokacje operatora (≥ 4 rowery razem), " +
            "pogoda i jakość powietrza (Open-Meteo), korki i utrudnienia (TomTom), wydarzenia, mapa OSM.\n\n" +
            "<b>Widoki stacji (V)</b>\n" +
            "Zapełnienie – wysokość = liczba rowerów, kolor = zapełnienie.\n" +
            "Bilans 1 h – które stacje tracą, a które zyskują rowery (zwroty − wypożyczenia w ostatniej godzinie).\n" +
            "H2: pustki – jak często stacja była pusta w całym okresie zbierania; czerwone = 10% najczęściej pustych.\n\n" +
            "<b>Sterowanie</b>\n" +
            "PPM / Shift+LPM – obrót · LPM (przeciągnij) – przesuwanie · kółko – zoom · WASD, Q/E\n" +
            "Klik na stację – karta stacji · Esc – zamknij\n" +
            "Spacja – start/pauza · ← → – 15 min · [ ] – wolniej/szybciej · , . – poprzedni/następny dzień\n" +
            "1 miasto · 2 Śródmieście · 3 z góry · 4 nad ulicami · 5 Wisła i mosty · C kamera kinowa\n" +
            "T – pokaz z komentarzem · X – dane | model tego dnia (Shift + , . zmienia prawy widok: dni i przebiegi modelu)\n" +
            "Z – do 4 strategii relokacji obok siebie (licznik utraconych klientów nad każdą) · N – główny widok: dane / model\n" +
            "J agenci modelu (czekają, idą do sąsiedniej stacji, odchodzą ✕) · O decyzje dyspozytora · B fale pustek · Y ciśnienie\n" +
            "F łuki OD · G ślady dnia · U utracony popyt · K korki · P mieszkańcy · M mapa · H ukryj panele\n" +
            "Klik na rower lub ciężarówkę – kamera jedzie za nim (Esc – koniec)\n" +
            "Warstwa Efekty – bloom, SSAO i odbicia w wodzie (wyłącz na słabszym komputerze)\n" +
            "F12 – zrzut ekranu (folder Screenshots obok projektu / aplikacji)";

        static Text KpiRow(Transform parent, string label, ref int y, Color c) => KpiRow(parent, label, ref y, c, out _);

        static Text KpiRow(Transform parent, string label, ref int y, Color c, out Text labelText)
        {
            Ui.Swatch(parent, c, new Vector2(18, y - 12), new Vector2(10, 10));
            labelText = Ui.Label(parent, label, 15, new Vector2(36, y - 6), new Vector2(260, 24), color: Ui.TextDim);
            var v = Ui.Label(parent, "–", 22, new Vector2(232, y - 3), new Vector2(200, 30), TextAnchor.UpperRight, style: FontStyle.Bold);
            y -= 36;
            return v;
        }

        static GameObject Legend(Transform parent, int y, (Color c, string label)[] rows)
        {
            var g = Ui.Rect("Legend", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, new Vector2(390, 140));
            foreach (var (c, label) in rows) LegendRow(g, c, label, ref y);
            return g.gameObject;
        }

        static void LegendCell(Transform parent, Color c, string label, int x, int y)
        {
            Ui.Swatch(parent, c, new Vector2(x, y - 3), new Vector2(14, 14));
            Ui.Label(parent, label, 13, new Vector2(x + 22, y), new Vector2(160, 20));
        }

        static void LegendRow(Transform parent, Color c, string label, ref int y)
        {
            Ui.Swatch(parent, c, new Vector2(16, y - 3), new Vector2(18, 14));
            Ui.Label(parent, label, 14, new Vector2(42, y), new Vector2(340, 20));
            y -= 22;
        }

        // ------------------------------------------------------------------ aktualizacja

        public void OnDayLoaded(DataStore d)
        {
            var k = d.Day.kpi;
            var tph = new float[25];
            for (int i = 0; i < tph.Length && i < k.tripsPerHour.Length; i++) tph[i] = k.tripsPerHour[i];
            tripsChart.SetValues(tph);
            timelineChart.SetValues(tph);
            var e = new float[50];
            for (int i = 0; i < e.Length; i++)
            {
                int s0 = i * 6;
                float sum = 0; int n = 0;
                for (int s = s0; s < s0 + 6 && s < k.empty.Length; s++) if (k.known[s] == 1) { sum += k.empty[s]; n++; }
                e[i] = n > 0 ? sum / n : 0;
            }
            emptyChart.SetValues(e);
            dayLabel.text = d.Day.label;
            title.text = (d.IsSim ? $"<color=#ff9f40>MODEL · {d.SourceLabel.Replace("MODEL · ", "")}</color>" : "VETURILO · dane rzeczywiste") +
                         $" · {d.Day.trips.dep.Length} przejazdów" + (d.Day.coverage < 0.95f ? $" · pokrycie {d.Day.coverage:P0}" : "");
            kLostLabel.text = d.IsSim ? "Utracony popyt od północy (model)" : "Utracony popyt od północy (szac.)";
            kTrucksLabel.text = d.IsSim ? "Kursy ciężarówek (model)" : "Relokacje operatora";
            chartFor = null;
        }

        public void UpdateAt(DataStore d, float t)
        {
            var day = d.Day;
            int slot = d.SlotAt(t);
            clock.text = d.ClockText(t);
            dateLine.text = $"{day.label}.{day.date.Substring(0, 4)} · {DataStore.DayTypeText(day.dayType)}" +
                            (day.uniClasses > 0 ? " · zajęcia na uczelniach" : "");

            var h = day.hours;
            float temp = d.HourValue(h.temp, t), feels = d.HourValue(h.apparentTemp, t);
            float precip = d.HourValue(h.precip, t), wind = d.HourValue(h.wind, t);
            float cong = d.HourValue(h.congestion, t), aqi = d.HourValue(h.aqi, t);
            int hi = d.HourIndex(t);
            string code = h.weatherCode != null && h.weatherCode.Length > hi ? DataStore.WeatherText(h.weatherCode[hi]) : "";
            tempBig.text = $"{temp:0.0}°C";
            weatherDesc.text = code + (precip > 0.05f ? $", {precip:0.0} mm/h" : "");
            float sunEl = app.Env.SunElevation;
            weather2.text = $"odczuwalna {feels:0}°C · wiatr {wind:0} km/h · " +
                            (sunEl < -6 ? "noc" : sunEl < 0 ? "zmierzch / świt" : $"słońce {sunEl:0}° nad horyzontem");
            weather3.text = (aqi > 0 ? $"powietrze {DataStore.AqiText(aqi)} (AQI {aqi:0}) · " : "") +
                            $"korki {cong * 100:0}%" +
                            (app.Context.ActiveIncidents > 0 ? $" · utrudnienia {app.Context.ActiveIncidents}" : "");
            eventsLine.text = app.Context.ActiveEvents > 0 ? "Teraz: " + app.Context.ActiveEventNames
                            : day.events != null && day.events.Length > 0 ? "Wydarzenia dziś: " + string.Join(", ", day.events) : "";
            if (d.IsSim)
                eventsLine.text = $"<color=#ffffff>Agenci: czeka {app.Agents.Waiting} · idzie {app.Agents.Walking} · odchodzi {app.Agents.Leaving}" +
                                  $" · zadania {app.Agents.ActiveTasks}</color>" + (app.Cascades.Active > 0 ? $"\n<color=#ff4d8c>fale pustek teraz: {app.Cascades.Active}</color>" : "");
            else if (app.Cascades.Active > 0 && app.LayerOn("Fale pustek"))
                eventsLine.text = $"<color=#ff4d8c>Fale pustek teraz: {app.Cascades.Active} ({app.Cascades.ActiveStations} stacji)</color>" +
                                  (eventsLine.text.Length > 0 ? "\n" + eventsLine.text : "");
            if (eventsLine.text.Length > 110) eventsLine.text = eventsLine.text.Substring(0, 107) + "...";

            var k = day.kpi;
            bool known = k.known[slot] == 1;
            kInUse.text = app.Bikes.ActiveCount.ToString();
            kTrips.text = $"{app.Bikes.StartedCount} <size=14><color=#9aa3b0>z {day.trips.dep.Length}</color></size>";
            kEmpty.text = known ? $"{k.empty[slot]} <size=14><color=#9aa3b0>z {d.Stations.Length}</color></size>" : "–";
            kOver.text = known ? k.overfull[slot].ToString() : "–";
            kTrucks.text = $"{app.Trucks.DoneCount} <size=14><color=#9aa3b0>({app.Trucks.BikesMovedToday} rowerów)</color></size>";
            int away = k.awayLong != null && k.awayLong.Length > slot ? k.awayLong[slot] : -1;
            kLost.text = d.IsSim ? $"{d.TotalLostAt(t):0} <size=14><color=#9aa3b0>osób</color></size>"
                       : d.HasLost ? $"≈ {d.TotalLostAt(t):0} <size=14><color=#9aa3b0>osób</color></size>" : "–";
            kFleet.text = (known ? k.atStations[slot].ToString() : "–") + (away >= 0 ? $" / {away}" : "");

            int hour = Mathf.Clamp(Mathf.FloorToInt(t / 3600f), 0, 24);
            tripsChart.SetHighlight(hour, hour);
            timelineChart.SetHighlight(hour, 24);
            emptyChart.SetHighlight(Mathf.FloorToInt(t / 1800f), Mathf.FloorToInt(t / 1800f));

            sliderLock = true;
            slider.value = t / Mathf.Max(day.lengthSec, 1);
            sliderLock = false;
            Ui.SetOn(play, !app.Playing);
            Ui.SetText(play, app.Playing ? "Pauza" : "Start");
            foreach (var (b, s) in speedButtons) Ui.SetOn(b, Mathf.Approximately(s, app.Speed));
            speedLabel.text = $"1 s = {app.Speed / 60f:0.#} min";
            Ui.SetOn(tourButton, app.TourRunning);
            Ui.SetOn(compareButton, app.Mode == VeturiloApp.CompareMode.Pair);
            Ui.SetOn(strategiesButton, app.Mode == VeturiloApp.CompareMode.Strategies);
            Ui.SetOn(modelButton, d.IsSim);
            if (app.Comparing) UpdateCompare(d, t);
            UpdateTicker(d, t);

            foreach (var kv in modeButtons) Ui.SetOn(kv.Value, kv.Key == app.Stations.Mode);
            foreach (var kv in legends) kv.Value.SetActive(kv.Key == app.Stations.Mode);
            modeDesc.text = ModeDescription(d);
            foreach (var kv in layerButtons) Ui.SetOn(kv.Value, app.LayerOn(kv.Key));

            UpdateStation(d, t);
            UpdateEmptyList(d, t);
            UpdateTooltip();
            if (captionPanel.gameObject.activeSelf && Time.unscaledTime > captionUntil) captionPanel.gameObject.SetActive(false);
        }

        string ModeDescription(DataStore d)
        {
            switch (app.Stations.Mode)
            {
                case ViewMode.Balance:
                    return "Wysokość = różnica zwrotów i wypożyczeń w ostatniej godzinie. Czerwone stacje pustoszeją – tam przyda się relokacja.";
                case ViewMode.Problem:
                    return $"Wysokość = udział czasu pustki (cały okres). 10% stacji = {d.Top10Share:P0}, 20% = {d.Top20Share:P0} czasu pustek; Gini {d.Gini:0.00}.";
                default:
                    return "Wysokość = liczba rowerów na stacji, kolor = zapełnienie względem liczby stojaków.";
            }
        }

        void UpdateStation(DataStore d, float t)
        {
            var v = app.Stations.Selected;
            stationPanel.gameObject.SetActive(v != null && Visible && !app.Comparing);
            emptyPanel.gameObject.SetActive(v == null && Visible && !app.Comparing);
            if (v == null) return;
            var s = v.Info;
            stName.text = s.name;
            stNow.text = v.Bikes < 0 ? "brak danych" : $"{v.Bikes:0} / {s.cap} rowerów" + (v.EBikes > 0.5f ? $" <size=16>· {v.EBikes:0} e-rowerów</size>" : "");
            stNow.color = Mats.StationColor(v.Bikes, s.cap);
            int rank = Mathf.RoundToInt(d.EmptyRank[v.Index] * (d.Stations.Length - 1)) + 1;
            int emptyMin = d.EmptyMinutes(v.Index, t);
            stInfo.text =
                $"ostatnia godzina: <color=#ffcc33>{v.Departures} wypożyczeń</color>, <color=#4dbfff>{v.Arrivals} zwrotów</color>" +
                (emptyMin > 0 ? $"  <color=#f23340>pusta od {emptyMin} min</color>" : "") +
                $"\npusta przez {s.shareEmpty:P0} czasu ({rank}. z {d.Stations.Length}) · przepełniona {s.shareOverfull:P0}" +
                $"\n300 m: {s.nRestaurants} lokali, {s.nBars + s.nCafes} barów/kawiarni, {s.nOffices} biur, {s.nUniversities} uczelni" +
                $"\n500 m: {s.population} mieszkańców · {s.transitDepartures} odjazdów komunikacji" +
                (d.HasLost ? $"\npopyt teraz ≈ {d.RateAt(v.Index, t):0.0}/h · utracony dziś ≈ {d.LostAt(v.Index, t):0.0} os." : "") +
                "\n" + (s.distMetro >= 0 ? $"metro {s.distMetro} m · " : "") + (s.distCenter >= 0 ? $"centrum {s.distCenter / 1000f:0.0} km · " : "") + $"{s.elevation:0} m n.p.m.";
            if (chartFor != v)
            {
                chartFor = v;
                var b = d.Day.states[v.Index].b;
                var vals = new float[96];
                for (int i = 0; i < 96; i++)
                {
                    int s0 = i * 3; float sum = 0; int n = 0;
                    for (int q = s0; q < s0 + 3 && q < b.Length; q++) if (b[q] >= 0) { sum += b[q]; n++; }
                    vals[i] = n > 0 ? sum / n : 0;
                }
                stationChart.SetValues(vals, Mathf.Max(s.cap * 1.5f, 1));
                var dep = new float[24]; var arr = new float[24];
                d.HourlyFlow(v.Index, dep, arr);
                var both = new float[48];
                for (int i = 0; i < 24; i++) { both[2 * i] = dep[i]; both[2 * i + 1] = arr[i]; }
                flowChart.SetValues(both);
            }
            int hour = Mathf.Clamp(Mathf.FloorToInt(t / 3600f), 0, 23);
            stationChart.SetHighlight(Mathf.FloorToInt(t / 900f), Mathf.FloorToInt(t / 900f));
            flowChart.SetHighlight(2 * hour, 2 * hour + 1, 2 * hour + 1);
        }

        void UpdateEmptyList(DataStore d, float t)
        {
            if (!emptyPanel.gameObject.activeSelf || Time.unscaledTime < nextListUpdate) return;
            nextListUpdate = Time.unscaledTime + 0.4f;
            var list = new List<(StationView v, int min)>();
            foreach (var v in app.Stations.Views)
            {
                int m = d.EmptyMinutes(v.Index, t);
                if (m > 0) list.Add((v, m));
            }
            list.Sort((a, b) => b.min.CompareTo(a.min));
            emptyTitle.text = list.Count > 0 ? $"Najdłużej puste teraz  <color=#f23340>({list.Count} pustych)</color>" : "Najdłużej puste teraz – brak pustych stacji";
            for (int i = 0; i < emptyRows.Length; i++)
            {
                bool on = i < list.Count;
                emptyRows[i].gameObject.SetActive(on);
                emptyRowStation[i] = on ? list[i].v : null;
                if (!on) continue;
                string name = list[i].v.Info.name;
                if (name.Length > 36) name = name.Substring(0, 35) + "…";
                string dur = list[i].min >= 60 ? $"{list[i].min / 60} h {list[i].min % 60:00} min" : $"{list[i].min} min";
                Ui.SetText(emptyRows[i], $"<color=#f23340>●</color> {name}  <color=#9aa3b0>{dur}</color>");
            }
        }

        void OnEmptyRow(int i)
        {
            var v = emptyRowStation[i];
            if (v != null) app.SelectStation(v);
        }

        void UpdateTooltip()
        {
            var v = app.Stations.Hovered;
            bool show = v != null && Visible && v != app.Stations.Selected;
            tooltipRect.gameObject.SetActive(show);
            if (!show) return;
            string extra = app.Stations.Mode == ViewMode.Balance ? $" · bilans 1 h: {v.Arrivals - v.Departures:+0;-0;0}"
                         : app.Stations.Mode == ViewMode.Problem ? $" · pusta {v.Info.shareEmpty:P0} czasu" : "";
            tooltip.text = $"{v.Info.name}   {(v.Bikes < 0 ? "–" : v.Bikes.ToString("0"))}/{v.Info.cap}{extra}";
            var scale = canvas.scaleFactor > 0 ? canvas.scaleFactor : 1f;
            tooltipRect.anchoredPosition = InputCompat.MousePosition / scale + new Vector2(16, 16);
        }

        public void SetFollow(string text)
        {
            if (followPanel == null) return;
            followPanel.gameObject.SetActive(text != null && !app.Comparing);
            if (text != null) followText.text = text;
        }

        void UpdateTicker(DataStore d, float t)
        {
            bool show = Visible && !app.Comparing && !followPanel.gameObject.activeSelf && !app.TourRunning;
            if (tickerPanel.gameObject.activeSelf != show) tickerPanel.gameObject.SetActive(show);
            if (!show) return;
            // okno 45 min czasu symulacji; najnowsze u gory, starsze przygaszone
            d.TickerAt(t, 2700f, 4, tickerItems);
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < tickerItems.Count; i++)
            {
                var it = tickerItems[i];
                var c = it.color; c.a = i == 0 ? 1f : 0.85f - 0.15f * i;
                sb.Append($"<color=#9aa3b0>{d.ClockText(it.t)}</color>  <color=#{ColorUtility.ToHtmlStringRGBA(c)}>{it.text}</color>");
                if (i < tickerItems.Count - 1) sb.Append('\n');
            }
            tickerText.text = tickerItems.Count > 0 ? sb.ToString() : "<color=#9aa3b0>spokojnie – brak zdarzeń w ostatnich 45 min</color>";
        }

        public void SetCompare(bool on)
        {
            foreach (var g in mainPanels) g.SetActive(!on && Visible);
            int n = on ? app.Panels.Count + 1 : 0;
            for (int k = 0; k < cmpPanels.Length; k++) cmpPanels[k].gameObject.SetActive(k < n);
            compareClock.gameObject.SetActive(on);
            followPanel.gameObject.SetActive(false);
            foreach (var r in dividers) r.gameObject.SetActive(false);
            if (!on) return;
            // linie podzialu: pionowe miedzy kolumnami, pozioma przy 4 panelach
            int div = 0;
            void Vertical(float x)
            {
                var r = dividers[div++];
                r.anchorMin = new Vector2(x, 0); r.anchorMax = new Vector2(x, 1); r.sizeDelta = new Vector2(3, 0);
                r.gameObject.SetActive(true);
            }
            if (n == 2 || n == 4) Vertical(0.5f);
            if (n == 3) { Vertical(1 / 3f); Vertical(2 / 3f); }
            if (n == 4)
            {
                var r = dividers[div++];
                r.anchorMin = new Vector2(0, 0.5f); r.anchorMax = new Vector2(1, 0.5f); r.sizeDelta = new Vector2(0, 3);
                r.gameObject.SetActive(true);
            }
            for (int k = 0; k < n; k++)
            {
                var rect = app.ViewRect(k);
                var r = cmpPanels[k];
                r.anchorMin = r.anchorMax = new Vector2(rect.x, rect.yMax);
                // w gornym srodku jest zegar - przy 2 kolumnach naglowek prawego panelu przesuwamy w prawo
                float x = k > 0 && Mathf.Approximately(rect.x, 0.5f) && rect.yMax > 0.99f ? 112f : 12f;
                r.anchoredPosition = new Vector2(x, rect.yMax > 0.99f ? -12f : -8f);
                r.sizeDelta = new Vector2(Mathf.Min(470f, rect.width * 1920f - x - 24f), 96f);
            }
        }

        void UpdateCompare(DataStore a, float t)
        {
            cmpClock.text = a.ClockText(t);
            cmpTexts[0].text = CompareText(a, t, app.Bikes.ActiveCount, app.Bikes.StartedCount, app.Mode == VeturiloApp.CompareMode.Strategies);
            for (int k = 0; k < app.Panels.Count && k + 1 < cmpTexts.Length; k++)
            {
                var p = app.Panels[k];
                cmpTexts[k + 1].text = CompareText(p.Data, p.Time, p.Bikes.ActiveCount, p.Bikes.StartedCount, app.Mode == VeturiloApp.CompareMode.Strategies);
            }
        }

        static string CompareText(DataStore d, float t, int inUse, int started, bool strategies)
        {
            var day = d.Day; int slot = d.SlotAt(t);
            bool known = day.kpi.known[slot] == 1;
            string head = d.IsSim ? $"<color=#ff9f40>MODEL</color> · {d.SourceLabel.Replace("MODEL · ", "")}"
                                  : $"<color=#ffcc33>DANE</color> · {day.label} · {DataStore.DayTypeText(day.dayType)}";
            float lost = d.TotalLostAt(t);
            string lostText = d.IsSim ? $"<size=26><b><color=#ff8095>{lost:0}</color></b></size> utraconych klientów"
                                      : d.HasLost ? $"<size=26><b><color=#ff8095>≈{lost:0}</color></b></size> utraconych (szac.)" : "";
            string km = d.IsSim && day.simKpi != null && strategies ? $" · {day.simKpi.truck_km:0} km/dobę" : "";
            return $"<b>{head}</b>\n{lostText}{km}\n" +
                   $"<color=#9aa3b0>w drodze</color> <b>{inUse}</b> · <color=#9aa3b0>przejazdy</color> <b>{started}</b>/{day.trips.dep.Length} · " +
                   $"<color=#9aa3b0>puste</color> <b><color=#f23340>{(known ? day.kpi.empty[slot].ToString() : "–")}</color></b>";
        }

        public void ShowCaption(string text, float seconds)
        {
            caption.text = text;
            captionUntil = Time.unscaledTime + seconds;
            captionPanel.gameObject.SetActive(true);
        }

        public void HideCaption() => captionPanel.gameObject.SetActive(false);

        public void ToggleVisible()
        {
            Visible = !Visible;
            foreach (Transform c in canvas.transform)
                if (c.name != "Help" && c.name != "Station" && c.name != "EmptyList" && c.name != "Tooltip" && c.name != "Caption" && c.name != "Message"
                    && c.name != "Follow" && !c.name.StartsWith("Compare") && c.name != "Divider" && c.name != "Ticker"
                    && !(app.Comparing && (c.name == "Info" || c.name == "KPI" || c.name == "View")))
                    c.gameObject.SetActive(Visible);
        }

        public void ToggleHelp() => helpPanel.gameObject.SetActive(!helpPanel.gameObject.activeSelf);
        public bool CloseHelp() { bool was = helpPanel.gameObject.activeSelf; helpPanel.gameObject.SetActive(false); return was; }

        public void ShowMessage(string text)
        {
            if (message == null) return;
            message.text = text;
        }
    }
}
