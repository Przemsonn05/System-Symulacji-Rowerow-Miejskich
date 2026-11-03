// Luki OD: najczestsze pary stacja -> stacja z ostatniej godziny jako luki nad miastem.
// Grubosc = liczba przejazdow, kolor od zoltego (start) do niebieskiego (cel) - widac kierunek przeplywu.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class FlowLayer : MonoBehaviour
    {
        public int maxArcs = 120;
        public float windowSec = 3600f;
        public int minTrips = 1;

        DataStore data;
        readonly List<LineRenderer> lines = new List<LineRenderer>();
        readonly Dictionary<long, int> counts = new Dictionary<long, int>();
        readonly List<KeyValuePair<long, int>> sorted = new List<KeyValuePair<long, int>>();
        Material mat;
        int lastSlot = -1;
        const int Segments = 28;

        public int ShownArcs { get; private set; }
        public int TopCount { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            mat = CityBuilder.Queue(Mats.Vertex(Color.white), 3030);
        }

        readonly List<float> strengths = new List<float>();

        public void OnDayLoaded() => lastSlot = -1;

        public void UpdateAt(float t)
        {
            if (!gameObject.activeSelf) return;
            // grubosc w pikselach mniej wiecej stala niezaleznie od odleglosci kamery
            var cam = Camera.main;
            float zoom = cam ? Mathf.Clamp(Mathf.Abs(cam.transform.position.y) / 3000f, 0.6f, 5f) : 1f;
            for (int i = 0; i < ShownArcs && i < strengths.Count; i++) lines[i].widthMultiplier = (5f + 22f * strengths[i]) * zoom;
            int slot = data.SlotAt(t);
            if (slot == lastSlot) return;
            lastSlot = slot;

            counts.Clear();
            var tr = data.Day.trips;
            for (int i = 0; i < tr.dep.Length; i++)
            {
                if (tr.dep[i] > t) break;
                if (tr.dep[i] < t - windowSec) continue;
                int a = tr.fromSt[i], b = tr.toSt[i];
                if (a < 0 || b < 0 || a == b) continue;
                long key = ((long)a << 20) | (long)b;
                counts.TryGetValue(key, out int c);
                counts[key] = c + 1;
            }
            sorted.Clear();
            foreach (var kv in counts) if (kv.Value >= minTrips) sorted.Add(kv);
            sorted.Sort((x, y) => y.Value.CompareTo(x.Value));
            int n = Mathf.Min(sorted.Count, maxArcs);
            TopCount = n > 0 ? sorted[0].Value : 0;

            strengths.Clear();
            for (int k = 0; k < n; k++)
            {
                var lr = Get(k);
                int a = (int)(sorted[k].Key >> 20), b = (int)(sorted[k].Key & 0xFFFFF);
                var sa = data.Stations[a]; var sb = data.Stations[b];
                Vector3 p0 = new Vector3(sa.x, 10f, sa.z), p1 = new Vector3(sb.x, 10f, sb.z);
                float dist = Vector3.Distance(p0, p1);
                float height = 120f + dist * 0.28f;
                for (int s = 0; s <= Segments; s++)
                {
                    float f = s / (float)Segments;
                    var p = Vector3.Lerp(p0, p1, f);
                    p.y += Mathf.Sin(f * Mathf.PI) * height;
                    lr.SetPosition(s, p);
                }
                float strength = Mathf.Clamp01(sorted[k].Value / (float)Mathf.Max(TopCount, 1));
                strengths.Add(strength);
                lr.widthMultiplier = (5f + 22f * strength) * zoom;
                var g = new Gradient();
                g.SetKeys(
                    new[] { new GradientColorKey(Mats.Bike, 0f), new GradientColorKey(Mats.EBike, 1f) },
                    new[] { new GradientAlphaKey(0.15f + 0.5f * strength, 0f), new GradientAlphaKey(0.35f + 0.6f * strength, 0.5f),
                            new GradientAlphaKey(0.25f + 0.6f * strength, 1f) });
                lr.colorGradient = g;
                lr.gameObject.SetActive(true);
            }
            for (int k = n; k < lines.Count; k++) lines[k].gameObject.SetActive(false);
            ShownArcs = n;
        }

        LineRenderer Get(int k)
        {
            if (k < lines.Count) return lines[k];
            var go = new GameObject("Arc");
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            var lr = go.AddComponent<LineRenderer>();
            lr.sharedMaterial = mat;
            lr.positionCount = Segments + 1;
            lr.useWorldSpace = true;
            lr.alignment = LineAlignment.View;
            lr.numCapVertices = 2;
            lr.shadowCastingMode = ShadowCastingMode.Off;
            lr.receiveShadows = false;
            lines.Add(lr);
            return lr;
        }
    }
}
