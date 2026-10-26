// Wczytanie danych z StreamingAssets/veturilo i funkcje pomocnicze (trasy, stan w czasie t).
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
        public Route[] BikeRoutes { get; private set; }
        public Route[] TruckRoutes { get; private set; }
        public DayFile Day { get; private set; }
        public int DayIndex { get; private set; } = -1;
        public string Error { get; private set; }

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
                return true;
            }
            catch (Exception e)
            {
                Error = $"Nie udalo sie wczytac danych z {Root}\n{e.Message}\n\n" +
                        "Uruchom w repozytorium:  python -m src.data.build  i  python -m src.viz.export";
                Debug.LogError(Error);
                return false;
            }
        }

        public bool LoadDay(int i)
        {
            i = Mathf.Clamp(i, 0, Index.days.Length - 1);
            try
            {
                Day = Read<DayFile>(Index.days[i].file);
                DayIndex = i;
                return true;
            }
            catch (Exception e)
            {
                Error = $"Nie udalo sie wczytac dnia {Index.days[i].file}: {e.Message}";
                Debug.LogError(Error);
                return false;
            }
        }

        /// Domyslny dzien: ostatni z pelnym pokryciem danych.
        public int DefaultDay()
        {
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
