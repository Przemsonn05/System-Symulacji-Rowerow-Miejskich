// Wczytanie danych z StreamingAssets/veturilo i funkcje pomocnicze (trasy, stan w czasie t, bilans stacji).
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Veturilo.Viz
{
    public class Route
    {
        public Vector2[] pts;
        public float[] cum;   // skumulowana dlugosc [m]
        public float length;

        public Route(int[] flat)
        {
            int n = flat.Length / 2;
            pts = new Vector2[Mathf.Max(n, 1)];
            for (int i = 0; i < n; i++) pts[i] = new Vector2(flat[2 * i], flat[2 * i + 1]);
            cum = new float[pts.Length];
            for (int i = 1; i < pts.Length; i++) cum[i] = cum[i - 1] + Vector2.Distance(pts[i - 1], pts[i]);
            length = cum[cum.Length - 1];
        }

        public Route(Vector2 a, Vector2 b)
        {
            pts = new[] { a, b };
            cum = new[] { 0f, Vector2.Distance(a, b) };
            length = cum[1];
        }

        /// Punkt na trasie dla ulamka f (0..1) i kierunek jazdy.
        public Vector2 Sample(float f, out Vector2 dir)
        {
            dir = Vector2.up;
            if (pts.Length == 1 || length <= 0.01f) return pts[0];
            float d = Mathf.Clamp01(f) * length;
            int lo = 0, hi = cum.Length - 1;
            while (hi - lo > 1)
            {
                int mid = (lo + hi) >> 1;
                if (cum[mid] <= d) lo = mid; else hi = mid;
            }
            float seg = cum[hi] - cum[lo];
            float t = seg > 0 ? (d - cum[lo]) / seg : 0f;
            Vector2 a = pts[lo], b = pts[hi];
            if (seg > 0) dir = (b - a) / seg;
            return Vector2.LerpUnclamped(a, b, t);
        }
    }

    public class DataStore
    {
        public string Root { get; private set; }
        public IndexFile Index { get; private set; }
        public StationInfo[] Stations { get; private set; }
        public CityFile City { get; private set; }
        public BasemapFile Basemap { get; private set; }
        public Route[] BikeRoutes { get; private set; }
        public Route[] TruckRoutes { get; private set; }
        public DayFile Day { get; private set; }
        public int DayIndex { get; private set; } = -1;
        public string Error { get; private set; }

        // H2: koncentracja pustek (z share_empty calego okresu zbierania)
        public float[] EmptyRank { get; private set; }   // 0 = najczesciej pusta .. 1 = najrzadziej
        public float Top10Share { get; private set; }
        public float Top20Share { get; private set; }
        public float NeverEmptyShare { get; private set; }
        public float Gini { get; private set; }

        // dzien: skumulowane wypozyczenia i zwroty na stacji (indeks = numer pomiaru 5 min)
        int[][] depCum, arrCum;
        List<int>[] looseBySlot, incidentsByStep;

        public bool Load()
        {
            Root = Path.Combine(Application.streamingAssetsPath, "veturilo");
            try
            {
                Index = Read<IndexFile>("index.json");
                Stations = Read<StationsFile>("stations.json").stations;
                City = Read<CityFile>("city.json");
                BikeRoutes = ToRoutes(Read<RoutesFile>("routes.json").routes);
                TruckRoutes = ToRoutes(Read<RoutesFile>("truck_routes.json").routes);
                if (Index.days == null || Index.days.Length == 0) throw new Exception("index.json nie zawiera dni");
            }
            catch (Exception e)
            {
                Error = $"Nie udało się wczytać danych z {Root}\n{e.Message}\n\n" +
                        "Uruchom w repozytorium:  python -m src.data.build  i  python -m src.viz.export";
                Debug.LogError(Error);
                return false;
            }
            // podklad jest opcjonalny (starszy eksport go nie ma)
            try { Basemap = Read<BasemapFile>("basemap.json"); }
            catch (Exception e) { Debug.LogWarning("Veturilo: brak podkładu mapy (" + e.Message + ")"); }
            ComputeConcentration();
            return true;
        }

        public bool LoadDay(int i)
        {
            i = Mathf.Clamp(i, 0, Index.days.Length - 1);
            try
            {
                Day = Read<DayFile>(Index.days[i].file);
                DayIndex = i;
            }
            catch (Exception e)
            {
                Error = $"Nie udało się wczytać dnia {Index.days[i].file}: {e.Message}";
                Debug.LogError(Error);
                return false;
            }
            IndexDay();
            return true;
        }

        /// Domyslny dzien: ostatni pelny dzien roboczy (najlepiej pokazuje szczyty), inaczej ostatni pelny.
        public int DefaultDay()
        {
            for (int i = Index.days.Length - 1; i >= 0; i--)
                if (Index.days[i].coverage >= 0.95f && Index.days[i].dayType == "workday") return i;
            for (int i = Index.days.Length - 1; i >= 0; i--)
                if (Index.days[i].coverage >= 0.95f) return i;
            return Index.days.Length - 1;
        }

        T Read<T>(string file)
        {
            string path = Path.Combine(Root, file);
            if (!File.Exists(path)) throw new FileNotFoundException("brak pliku " + file);
            return JsonUtility.FromJson<T>(File.ReadAllText(path));
        }

        static Route[] ToRoutes(Polyline[] src)
        {
            if (src == null) return new Route[0];
            var r = new Route[src.Length];
            for (int i = 0; i < src.Length; i++) r[i] = new Route(src[i].p ?? new int[2]);
            return r;
        }

        void ComputeConcentration()
        {
            int n = Stations.Length;
            var order = new int[n];
            for (int i = 0; i < n; i++) order[i] = i;
            Array.Sort(order, (a, b) => Stations[b].shareEmpty.CompareTo(Stations[a].shareEmpty));
            EmptyRank = new float[n];
            float total = 0, top10 = 0, top20 = 0; int never = 0;
            for (int r = 0; r < n; r++)
            {
                float v = Stations[order[r]].shareEmpty;
                EmptyRank[order[r]] = n > 1 ? r / (float)(n - 1) : 0;
                total += v;
                if (r < Mathf.CeilToInt(n * 0.1f)) top10 += v;
                if (r < Mathf.CeilToInt(n * 0.2f)) top20 += v;
                if (v <= 0) never++;
            }
            Top10Share = total > 0 ? top10 / total : 0;
            Top20Share = total > 0 ? top20 / total : 0;
            NeverEmptyShare = n > 0 ? never / (float)n : 0;
            // Gini: posortowane rosnaco
            float g = 0;
            for (int r = 0; r < n; r++) g += (2 * (r + 1) - n - 1) * Stations[order[n - 1 - r]].shareEmpty;
            Gini = total > 0 ? g / (n * total) : 0;
        }

        void IndexDay()
        {
            int n = Stations.Length, slots = SlotCount;
            depCum = new int[n][]; arrCum = new int[n][];
            for (int s = 0; s < n; s++) { depCum[s] = new int[slots + 1]; arrCum[s] = new int[slots + 1]; }
            var tr = Day.trips;
            for (int i = 0; i < tr.dep.Length; i++)
            {
                int a = tr.fromSt[i], b = tr.toSt[i];
                if (a >= 0 && a < n) depCum[a][Mathf.Clamp(tr.dep[i] / Day.slotSec + 1, 1, slots)]++;
                if (b >= 0 && b < n) arrCum[b][Mathf.Clamp(tr.arr[i] / Day.slotSec + 1, 1, slots)]++;
            }
            for (int s = 0; s < n; s++)
                for (int k = 1; k <= slots; k++) { depCum[s][k] += depCum[s][k - 1]; arrCum[s][k] += arrCum[s][k - 1]; }

            looseBySlot = new List<int>[slots];
            for (int k = 0; k < slots; k++) looseBySlot[k] = new List<int>();
            var lo = Day.loose;
            if (lo?.slot != null)
                for (int i = 0; i < lo.slot.Length; i++)
                    if (lo.slot[i] >= 0 && lo.slot[i] < slots) looseBySlot[lo.slot[i]].Add(i);

            int steps = Mathf.CeilToInt(Day.lengthSec / 1800f);
            incidentsByStep = new List<int>[steps];
            for (int k = 0; k < steps; k++) incidentsByStep[k] = new List<int>();
            var inc = Day.incidents;
            if (inc?.step != null)
                for (int i = 0; i < inc.step.Length; i++)
                    if (inc.step[i] >= 0 && inc.step[i] < steps) incidentsByStep[inc.step[i]].Add(i);
        }

        // ---------------------------------------------------------------- czas

        public int SlotCount => Day?.states != null && Day.states.Length > 0 ? Day.states[0].b.Length : 0;

        /// Liczba rowerow na stacji w chwili t (interpolacja miedzy pomiarami co 5 min). -1 = brak danych.
        /// ebikes = -1, gdy brak danych o e-rowerach (pomiary sprzed 23.10.2026 ok. 10:00).
        public float BikesAt(int station, float t, out float ebikes)
        {
            ebikes = -1;
            var s = Day.states[station];
            float slot = t / Day.slotSec;
            int i = Mathf.Clamp(Mathf.FloorToInt(slot), 0, s.b.Length - 1);
            int j = Mathf.Min(i + 1, s.b.Length - 1);
            if (s.b[i] < 0) return -1;
            float f = slot - i;
            float b = s.b[j] < 0 ? s.b[i] : Mathf.Lerp(s.b[i], s.b[j], f);
            if (s.e[i] >= 0) ebikes = s.e[j] < 0 ? s.e[i] : Mathf.Lerp(s.e[i], s.e[j], f);
            return b;
        }

        public int SlotAt(float t) => Mathf.Clamp(Mathf.FloorToInt(t / Day.slotSec), 0, Mathf.Max(SlotCount - 1, 0));

        /// Wypozyczenia i zwroty na stacji w oknie (t - window, t].
        public void FlowAt(int station, float t, float window, out int departures, out int arrivals)
        {
            int slots = SlotCount;
            int k1 = Mathf.Clamp(Mathf.FloorToInt(t / Day.slotSec) + 1, 0, slots);
            int k0 = Mathf.Clamp(Mathf.FloorToInt((t - window) / Day.slotSec) + 1, 0, slots);
            departures = depCum[station][k1] - depCum[station][k0];
            arrivals = arrCum[station][k1] - arrCum[station][k0];
        }

        /// Wypozyczenia / zwroty stacji w kazdej godzinie dnia.
        public void HourlyFlow(int station, float[] dep, float[] arr)
        {
            int perHour = 3600 / Day.slotSec, slots = SlotCount;
            for (int h = 0; h < dep.Length; h++)
            {
                int k0 = Mathf.Min(h * perHour, slots), k1 = Mathf.Min((h + 1) * perHour, slots);
                dep[h] = depCum[station][k1] - depCum[station][k0];
                arr[h] = arrCum[station][k1] - arrCum[station][k0];
            }
        }

        /// Ile minut stacja jest pusta bez przerwy do chwili t (0 = nie jest pusta, -1 = brak danych).
        public int EmptyMinutes(int station, float t)
        {
            var b = Day.states[station].b;
            int k = SlotAt(t);
            if (b[k] < 0) return -1;
            if (b[k] > 0) return 0;
            int n = 0;
            while (k - n >= 0 && b[k - n] == 0) n++;
            return n * Day.slotSec / 60;
        }

        public List<int> LooseAt(float t) => looseBySlot != null && looseBySlot.Length > 0
            ? looseBySlot[SlotAt(t)] : new List<int>();

        public int StepAt(float t) => Mathf.Clamp(Mathf.FloorToInt(t / 1800f), 0, Mathf.Max(incidentsByStep.Length - 1, 0));
        public List<int> IncidentsAt(float t) => incidentsByStep != null && incidentsByStep.Length > 0
            ? incidentsByStep[StepAt(t)] : new List<int>();

        /// Korki na korytarzu w chwili t (ostatni znany pomiar do 1 h wstecz); -1 = brak danych.
        public float CongestionAt(Corridor c, float t)
        {
            if (c.cong == null || c.cong.Length == 0) return -1;
            int k = Mathf.Clamp(Mathf.FloorToInt(t / 1800f), 0, c.cong.Length - 1);
            for (int back = 0; back <= 2 && k - back >= 0; back++)
                if (c.cong[k - back] >= 0) return c.cong[k - back];
            return -1;
        }

        /// Wartosc godzinowa interpolowana liniowo (t w sekundach od polnocy).
        public float HourValue(float[] arr, float t)
        {
            if (arr == null || arr.Length == 0) return 0;
            float h = t / 3600f - 0.5f;
            int i = Mathf.Clamp(Mathf.FloorToInt(h), 0, arr.Length - 1);
            int j = Mathf.Min(i + 1, arr.Length - 1);
            return Mathf.Lerp(arr[i], arr[j], Mathf.Clamp01(h - i));
        }

        public int HourIndex(float t) => Day.hours.localHour == null || Day.hours.localHour.Length == 0
            ? 0 : Mathf.Clamp(Mathf.FloorToInt(t / 3600f), 0, Day.hours.localHour.Length - 1);

        public string ClockText(float t)
        {
            var local = DateTimeOffset.FromUnixTimeSeconds(Day.startEpoch + (long)t).ToOffset(LocalOffset(t));
            return local.ToString("HH:mm");
        }

        /// Godzina lokalna jako liczba (np. 7.5 = 7:30) - do zdarzen pokazu.
        public float LocalHour(float t)
        {
            var local = DateTimeOffset.FromUnixTimeSeconds(Day.startEpoch + (long)t).ToOffset(LocalOffset(t));
            return local.Hour + local.Minute / 60f;
        }

        /// Czas od polnocy [s] dla godziny lokalnej (uwzglednia dzien zmiany czasu).
        public float TimeOfLocalHour(float hour)
        {
            float t = hour * 3600f;
            int diff = Day.lengthSec - 86400;
            if (diff > 0 && hour >= 3) t += 3600;   // jesienia 2:00-3:00 jest dwa razy
            if (diff < 0 && hour >= 3) t -= 3600;
            return Mathf.Clamp(t, 0, Day.lengthSec - 1);
        }

        // Strefa Europe/Warsaw bez bazy stref (dziala tak samo na kazdym systemie):
        // przesuniecie z poczatku dnia, a w dzien zmiany czasu przelaczenie o 03:00 / 02:00.
        TimeSpan LocalOffset(float t)
        {
            int start = Day.tzOffsetSec;
            int lengthDiff = Day.lengthSec - 86400; // +3600 jesienia, -3600 wiosna
            int offset = start;
            if (lengthDiff > 0 && t >= 3 * 3600) offset = start - 3600;
            if (lengthDiff < 0 && t >= 2 * 3600) offset = start + 3600;
            return TimeSpan.FromSeconds(offset);
        }

        public static string WeatherText(int code)
        {
            if (code == 0) return "bezchmurnie";
            if (code <= 2) return "małe zachmurzenie";
            if (code == 3) return "pochmurno";
            if (code == 45 || code == 48) return "mgła";
            if (code >= 51 && code <= 57) return "mżawka";
            if (code >= 61 && code <= 67) return "deszcz";
            if (code >= 71 && code <= 77) return "śnieg";
            if (code >= 80 && code <= 82) return "przelotny deszcz";
            if (code >= 85 && code <= 86) return "przelotny śnieg";
            if (code >= 95) return "burza";
            return "—";
        }

        public static string AqiText(float aqi)
        {
            if (aqi <= 0) return "";
            if (aqi <= 20) return "bardzo dobre";
            if (aqi <= 40) return "dobre";
            if (aqi <= 60) return "umiarkowane";
            if (aqi <= 80) return "złe";
            return "bardzo złe";
        }

        public static string DayTypeText(string t)
        {
            switch (t)
            {
                case "workday": return "dzień roboczy";
                case "saturday": return "sobota";
                case "sunday": return "niedziela";
                case "sunday_holiday": return "niedziela / święto";
                case "holiday": return "święto";
                case "weekend": return "weekend";
                default: return string.IsNullOrEmpty(t) ? "" : t;
            }
        }
    }
}
