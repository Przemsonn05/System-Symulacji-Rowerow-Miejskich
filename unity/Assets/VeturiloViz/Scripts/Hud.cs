// Panel informacyjny: zegar, pogoda, KPI, wykresy dnia, os czasu, warstwy, legenda, karta stacji, pomoc.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Veturilo.Viz
{
    public class Hud
    {
        readonly VeturiloApp app;
        Canvas canvas;
        Text title, dateLine, clock, weather, eventsLine, source, dayLabel, speedLabel, tooltip, hint, help, message;
        Text kInUse, kTrips, kEmpty, kOver, kTrucks, kAtStations;
        BarChart tripsChart, emptyChart, stationChart;
        Slider slider;
        Button play;
        readonly List<(Button b, float speed)> speedButtons = new List<(Button, float)>();
        readonly Dictionary<string, Button> layerButtons = new Dictionary<string, Button>();
        RectTransform stationPanel, helpPanel, tooltipRect;
        Text stName, stNow, stInfo;
        bool sliderLock;
        StationView chartFor;

        public bool Visible { get; private set; } = true;

        public Hud(VeturiloApp app) { this.app = app; }

        public void Build()
        {
            canvas = Ui.CreateCanvas(app.transform);
            var root = canvas.transform;

            // ------------------------------------------------ lewy gorny: zegar i kontekst
            var top = Ui.Panel("TopLeft", root, new Vector2(0, 1), new Vector2(20, -20), new Vector2(470, 240));
            title = Ui.Label(top, "VETURILO · system roweru miejskiego", 17, new Vector2(18, -12), new Vector2(440, 24), color: Ui.Accent, style: FontStyle.Bold);
            dateLine = Ui.Label(top, "", 19, new Vector2(18, -40), new Vector2(440, 26));
            clock = Ui.Label(top, "--:--", 64, new Vector2(14, -64), new Vector2(300, 76), style: FontStyle.Bold);
            weather = Ui.Label(top, "", 17, new Vector2(18, -142), new Vector2(440, 48), color: Ui.TextDim);
            eventsLine = Ui.Label(top, "", 14, new Vector2(18, -190), new Vector2(440, 20), color: Ui.Accent);
            source = Ui.Label(top, "", 13, new Vector2(18, -212), new Vector2(440, 20), color: Ui.TextDim);

            // ------------------------------------------------ lewy: KPI i wykresy
            var kpi = Ui.Panel("KPI", root, new Vector2(0, 1), new Vector2(20, -272), new Vector2(470, 520));
            int y = -14;
            kInUse = KpiRow(kpi, "Rowery w drodze", ref y, Mats.Bike);
            kTrips = KpiRow(kpi, "Przejazdy od północy", ref y, Ui.TextMain);
            kEmpty = KpiRow(kpi, "Puste stacje", ref y, Mats.Empty);
            kOver = KpiRow(kpi, "Stacje ponad pojemność", ref y, Mats.Overfull);
            kAtStations = KpiRow(kpi, "Rowery na stacjach", ref y, Mats.Ok);
            kTrucks = KpiRow(kpi, "Relokacje operatora", ref y, Mats.Truck);
            Ui.Label(kpi, "Przejazdy na godzinę", 15, new Vector2(18, y - 8), new Vector2(430, 20), color: Ui.TextDim);
            tripsChart = new BarChart(kpi, new Vector2(18, y - 32), new Vector2(434, 90), 25, new Color(1f, 0.8f, 0.2f, 0.55f), Ui.Accent);
            Ui.Label(kpi, "Puste stacje w ciągu dnia (co 30 min)", 15, new Vector2(18, y - 134), new Vector2(430, 20), color: Ui.TextDim);
            emptyChart = new BarChart(kpi, new Vector2(18, y - 158), new Vector2(434, 70), 50, new Color(0.95f, 0.2f, 0.25f, 0.5f), Mats.Empty);

            // ------------------------------------------------ prawy gorny: legenda i warstwy
            var legend = Ui.Panel("Legend", root, new Vector2(1, 1), new Vector2(-20, -20), new Vector2(300, 330));
            Ui.Label(legend, "Stacje (wysokość = liczba rowerów)", 15, new Vector2(16, -12), new Vector2(280, 22), color: Ui.TextDim);
            int ly = -40;
            LegendRow(legend, Mats.Empty, "pusta (pulsuje)", ref ly);
            LegendRow(legend, Mats.Low, "mało rowerów (< 25%)", ref ly);
            LegendRow(legend, Mats.Ok, "w normie", ref ly);
            LegendRow(legend, Mats.Full, "pełna", ref ly);
            LegendRow(legend, Mats.Overfull, "ponad pojemność", ref ly);
            LegendRow(legend, Mats.Bike, "rower w drodze", ref ly);
            LegendRow(legend, Mats.EBike, "e-rower w drodze", ref ly);
            LegendRow(legend, Mats.Truck, "ciężarówka (relokacja)", ref ly);
            Ui.Label(legend, "Warstwy", 15, new Vector2(16, ly - 6), new Vector2(280, 22), color: Ui.TextDim);
            int bx = 16, by = ly - 32;
            foreach (var name in new[] { "Budynki", "Drogi rower.", "Ślady", "Ciężarówki", "Opisy" })
            {
                string n = name;
                var b = Ui.Button(legend, n, new Vector2(bx, by), new Vector2(130, 30), () => app.ToggleLayer(n), 15);
                layerButtons[n] = b;
                Ui.SetOn(b, true);
                bx += 138;
                if (bx > 200) { bx = 16; by -= 36; }
            }

            // ------------------------------------------------ prawy: karta stacji
            stationPanel = Ui.Panel("Station", root, new Vector2(1, 1), new Vector2(-20, -370), new Vector2(300, 330));
            stName = Ui.Label(stationPanel, "", 18, new Vector2(16, -12), new Vector2(270, 48), style: FontStyle.Bold);
            stNow = Ui.Label(stationPanel, "", 30, new Vector2(16, -60), new Vector2(270, 40), style: FontStyle.Bold);
            stInfo = Ui.Label(stationPanel, "", 14, new Vector2(16, -102), new Vector2(270, 110), color: Ui.TextDim);
            Ui.Label(stationPanel, "Rowery na stacji w ciągu dnia", 13, new Vector2(16, -216), new Vector2(270, 18), color: Ui.TextDim);
            stationChart = new BarChart(stationPanel, new Vector2(16, -238), new Vector2(268, 72), 96, new Color(0.25f, 0.85f, 0.45f, 0.6f), Color.white);
            stationPanel.gameObject.SetActive(false);

            // ------------------------------------------------ dol: os czasu
            var bar = Ui.Rect("Timeline", root, new Vector2(0, 0), new Vector2(1, 0), new Vector2(0.5f, 0), new Vector2(0, 20), new Vector2(-40, 92));
            bar.gameObject.AddComponent<Image>().color = Ui.PanelBg;
            Ui.Button(bar, "<", new Vector2(14, -14), new Vector2(40, 32), () => app.ChangeDay(-1));
            dayLabel = Ui.Label(bar, "", 18, new Vector2(58, -14), new Vector2(130, 32), TextAnchor.MiddleCenter);
            Ui.Button(bar, ">", new Vector2(190, -14), new Vector2(40, 32), () => app.ChangeDay(+1));
            play = Ui.Button(bar, "Pauza", new Vector2(250, -14), new Vector2(70, 32), () => app.TogglePlay(), 18);
            int sx = 330;
            foreach (var sp in new[] { 60f, 300f, 900f, 1800f })
            {
                float s = sp;
                var b = Ui.Button(bar, "×" + s, new Vector2(sx, -14), new Vector2(66, 32), () => app.SetSpeed(s), 15);
                speedButtons.Add((b, s));
                sx += 72;
            }
            speedLabel = Ui.Label(bar, "", 14, new Vector2(sx + 6, -18), new Vector2(200, 26), color: Ui.TextDim);
            slider = Ui.Slider(bar, new Vector2(14, -54), new Vector2(1820, 26), v => { if (!sliderLock) app.Seek(v); });
            var sr = slider.GetComponent<RectTransform>();
            sr.anchorMin = new Vector2(0, 1); sr.anchorMax = new Vector2(1, 1); sr.sizeDelta = new Vector2(-28, 26);
            for (int h = 0; h <= 24; h += 3)
            {
                var tick = Ui.Label(bar, h.ToString("00") + ":00", 12, Vector2.zero, new Vector2(60, 16), TextAnchor.UpperCenter, Ui.TextDim);
                var tr = tick.rectTransform;
                tr.anchorMin = tr.anchorMax = new Vector2(0.0075f + 0.985f * h / 24f, 0);
                tr.pivot = new Vector2(0.5f, 0);
                tr.anchoredPosition = new Vector2(0, 2);
            }

            hint = Ui.Label(root, "F1 – pomoc   H – ukryj panel   C – kamera kinowa", 14, Vector2.zero, new Vector2(520, 20), TextAnchor.LowerRight, Ui.TextDim);
            hint.rectTransform.anchorMin = hint.rectTransform.anchorMax = hint.rectTransform.pivot = new Vector2(1, 0);
            hint.rectTransform.anchoredPosition = new Vector2(-24, 120);

            // tooltip stacji
            tooltipRect = Ui.Panel("Tooltip", root, new Vector2(0, 0), Vector2.zero, new Vector2(320, 34), new Color(0, 0, 0, 0.8f));
            tooltipRect.pivot = new Vector2(0, 0);
            tooltip = Ui.Label(tooltipRect, "", 15, new Vector2(10, -7), new Vector2(300, 24));
            tooltipRect.gameObject.SetActive(false);

            // pomoc
            helpPanel = Ui.Panel("Help", root, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(620, 420), new Color(0.03f, 0.04f, 0.06f, 0.94f));
            helpPanel.pivot = new Vector2(0.5f, 0.5f);
            help = Ui.Label(helpPanel, HelpText, 17, new Vector2(28, -22), new Vector2(570, 380));
            helpPanel.gameObject.SetActive(false);

            message = Ui.Label(root, "", 22, Vector2.zero, new Vector2(1100, 300), TextAnchor.MiddleCenter, Ui.TextMain);
            message.rectTransform.anchorMin = message.rectTransform.anchorMax = message.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            message.rectTransform.anchoredPosition = Vector2.zero;
        }

        const string HelpText =
            "<b>Sterowanie</b>\n\n" +
            "PPM / Shift+LPM – obrót kamery        LPM (przeciągnij) – przesuwanie\n" +
            "Kółko – przybliżenie        WASD – ruch, Q/E – obrót\n" +
            "Klik na stację – karta stacji i kamera do stacji\n\n" +
            "Spacja – start / pauza        strzałki lewo / prawo – 15 min wstecz / naprzód\n" +
            "[ / ] – wolniej / szybciej        , / . – poprzedni / następny dzień\n" +
            "1 – całe miasto   2 – Śródmieście   3 – widok z góry   4 – nisko nad ulicami\n" +
            "C – kamera kinowa (do nagrania filmu)        H – ukryj interfejs\n" +
            "R – reset widoku        Esc – zamknij kartę stacji / pomoc\n\n" +
            "<b>Dane</b>\n\n" +
            "Stan 340+ stacji co 5 min i pojedyncze przejazdy odtworzone z numerów rowerów " +
            "(feed nextbike-live), relokacje operatora (≥ 4 rowery razem), pogoda Open-Meteo, " +
            "korki TomTom. Czas przejazdu znany z dokładnością ±5 min.";

        static Text KpiRow(Transform parent, string label, ref int y, Color c)
        {
            var dot = Ui.Rect("Dot", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, y - 14), new Vector2(10, 10));
            dot.gameObject.AddComponent<Image>().color = c;
            Ui.Label(parent, label, 17, new Vector2(38, y - 6), new Vector2(280, 26), color: Ui.TextDim);
            var v = Ui.Label(parent, "–", 26, new Vector2(250, y - 2), new Vector2(200, 32), TextAnchor.UpperRight, style: FontStyle.Bold);
            y -= 40;
            return v;
        }

        static void LegendRow(Transform parent, Color c, string label, ref int y)
        {
            var sw = Ui.Rect("Swatch", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, y - 3), new Vector2(18, 14));
            sw.gameObject.AddComponent<Image>().color = c;
            Ui.Label(parent, label, 15, new Vector2(42, y), new Vector2(250, 20));
            y -= 24;
        }

        // ------------------------------------------------------------------ aktualizacja

        public void OnDayLoaded(DataStore d)
        {
            var k = d.Day.kpi;
            var tph = new float[25];
            for (int i = 0; i < tph.Length && i < k.tripsPerHour.Length; i++) tph[i] = k.tripsPerHour[i];
            tripsChart.SetValues(tph);
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
            source.text = (d.Index.source == "sim" ? "SYMULACJA DES" : "Dane rzeczywiste") +
                          $" · {d.Day.trips.dep.Length} przejazdów · pokrycie {d.Day.coverage:P0}";
            chartFor = null;
        }

        public void UpdateAt(DataStore d, float t)
        {
            var day = d.Day;
            int slot = d.SlotAt(t);
            clock.text = d.ClockText(t);
            dateLine.text = $"{day.label}.{day.date.Substring(0, 4)} · {DataStore.DayTypeText(day.dayType)}" +
                            (day.uniClasses > 0 ? " · zajęcia na uczelniach" : "");
            var evs = day.events != null && day.events.Length > 0 ? "Wydarzenia: " + string.Join(", ", day.events) : "";
            eventsLine.text = evs.Length > 62 ? evs.Substring(0, 59) + "..." : evs;

            float temp = d.HourValue(day.hours.temp, t);
            float precip = d.HourValue(day.hours.precip, t);
            float cong = d.HourValue(day.hours.congestion, t);
            int hi = d.HourIndex(t);
            string code = day.hours.weatherCode != null && day.hours.weatherCode.Length > hi ? DataStore.WeatherText(day.hours.weatherCode[hi]) : "";
            weather.text = $"{temp:0.0} °C · {code}" + (precip > 0.05f ? $" {precip:0.0} mm/h" : "") +
                           $"\nkorki: {cong * 100:0}% spowolnienia · słońce {app.Env.SunElevation:0}°";

            var k = day.kpi;
            kInUse.text = app.Bikes.ActiveCount.ToString();
            kTrips.text = app.Bikes.StartedCount.ToString();
            bool known = k.known[slot] == 1;
            kEmpty.text = known ? $"{k.empty[slot]} / {d.Stations.Length}" : "–";
            kOver.text = known ? k.overfull[slot].ToString() : "–";
            kAtStations.text = known ? k.atStations[slot].ToString() : "–";
            kTrucks.text = $"{app.Trucks.DoneCount} ({app.Trucks.BikesMovedToday} rowerów)" + (app.Trucks.ActiveCount > 0 ? $" · {app.Trucks.ActiveCount} w drodze" : "");

            int hour = Mathf.Clamp(Mathf.FloorToInt(t / 3600f), 0, 24);
            tripsChart.SetHighlight(hour, hour);
            emptyChart.SetHighlight(Mathf.FloorToInt(t / 1800f), Mathf.FloorToInt(t / 1800f));

            sliderLock = true;
            slider.value = t / Mathf.Max(day.lengthSec, 1);
            sliderLock = false;
            Ui.SetOn(play, !app.Playing);
            play.GetComponentInChildren<Text>().text = app.Playing ? "Pauza" : "Start";
            foreach (var (b, s) in speedButtons) Ui.SetOn(b, Mathf.Approximately(s, app.Speed));
            speedLabel.text = $"1 s = {app.Speed / 60f:0.#} min";

            UpdateStation(d, t);
            UpdateTooltip();
        }

        void UpdateStation(DataStore d, float t)
        {
            var v = app.Stations.Selected;
            stationPanel.gameObject.SetActive(v != null && Visible);
            if (v == null) return;
            var s = v.Info;
            stName.text = s.name;
            stNow.text = v.Bikes < 0 ? "brak danych" : $"{v.Bikes:0} / {s.cap} rowerów";
            stNow.color = Mats.StationColor(v.Bikes, s.cap);
            stInfo.text = (v.EBikes < 0 ? "e-rowery: brak danych\n" : $"e-rowery: {v.EBikes:0}\n") +
                          $"pusta przez {s.shareEmpty:P0} czasu, ponad pojemność {s.shareOverfull:P0}\n" +
                          $"w promieniu 300 m: {s.nRestaurants} lokali, {s.nOffices} biur, {s.nUniversities} uczelni\n" +
                          (s.distMetro >= 0 ? $"metro: {s.distMetro} m · " : "") + $"{s.elevation:0} m n.p.m. · id {s.id}";
            if (chartFor != v)
            {
                chartFor = v;
                var b = d.Day.states[v.Index].b;
                var vals = new float[96];
                for (int i = 0; i < 96; i++)
                {
                    int s0 = i * 3; float sum = 0; int n = 0;
                    for (int k = s0; k < s0 + 3 && k < b.Length; k++) if (b[k] >= 0) { sum += b[k]; n++; }
                    vals[i] = n > 0 ? sum / n : 0;
                }
                stationChart.SetValues(vals, Mathf.Max(s.cap * 1.5f, 1));
            }
            stationChart.SetHighlight(Mathf.FloorToInt(t / 900f));
        }

        void UpdateTooltip()
        {
            var v = app.Stations.Hovered;
            bool show = v != null && Visible && v != app.Stations.Selected;
            tooltipRect.gameObject.SetActive(show);
            if (!show) return;
            tooltip.text = $"{v.Info.name}   {(v.Bikes < 0 ? "–" : v.Bikes.ToString("0"))}/{v.Info.cap}";
            var scale = canvas.scaleFactor > 0 ? canvas.scaleFactor : 1f;
            tooltipRect.anchoredPosition = InputCompat.MousePosition / scale + new Vector2(16, 16);
        }

        public void SetLayerButton(string name, bool on) { if (layerButtons.TryGetValue(name, out var b)) Ui.SetOn(b, on); }

        public void ToggleVisible()
        {
            Visible = !Visible;
            foreach (Transform c in canvas.transform)
                if (c.name != "Help" && c.name != "Station" && c.name != "Tooltip") c.gameObject.SetActive(Visible);
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
