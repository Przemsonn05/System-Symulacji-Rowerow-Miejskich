// Rowery w drodze: kazdy przejazd z danych to swiecacy punkt jadacy po trasie, ze sladem.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class BikeLayer : MonoBehaviour
    {
        public float trailSimSeconds = 150f;   // dlugosc sladu w czasie symulacji
        public float minSize = 4f, maxSize = 30f;
        public bool showTrails = true;

        class Bike
        {
            public GameObject go;
            public MeshRenderer r;
            public TrailRenderer trail;
            public int trip = -1;
        }

        DataStore data;
        readonly List<Bike> pool = new List<Bike>();
        readonly Dictionary<int, Bike> active = new Dictionary<int, Bike>();
        readonly List<int> toRemove = new List<int>();
        Route[] looseRoutes;
        Material bikeMat, ebikeMat, trailMat;
        Mesh mesh;
        int next;           // indeks pierwszego przejazdu, ktory jeszcze nie wystartowal
        float lastT = -1;
        float lastSpeed = -1;
        Camera cam;

        public int ActiveCount => active.Count;
        public int StartedCount => next;

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            bikeMat = Mats.Unlit(Mats.Bike);
            ebikeMat = Mats.Unlit(Mats.EBike);
            trailMat = Mats.Vertex(Color.white);
            var tmp = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            mesh = tmp.GetComponent<MeshFilter>().sharedMesh;
            Destroy(tmp);
        }

        public void OnDayLoaded()
        {
            foreach (var b in active.Values) Release(b);
            active.Clear();
            next = 0; lastT = -1;
            var tr = data.Day.trips;
            looseRoutes = new Route[tr.dep.Length];
            for (int i = 0; i < tr.dep.Length; i++)
                if (tr.route[i] < 0) looseRoutes[i] = new Route(new Vector2(tr.fx[i], tr.fz[i]), new Vector2(tr.tx[i], tr.tz[i]));
        }

        Route RouteOf(int i)
        {
            int r = data.Day.trips.route[i];
            return r >= 0 && r < data.BikeRoutes.Length ? data.BikeRoutes[r] : looseRoutes[i];
        }

        public void UpdateAt(float t, float simSpeed)
        {
            var tr = data.Day.trips;
            int n = tr.dep.Length;
            // skok w tyl albo duzy skok w przod (suwak) - przebudowa listy aktywnych
            if (t < lastT || t - lastT > 900f)
            {
                foreach (var b in active.Values) Release(b);
                active.Clear();
                next = 0;
                while (next < n && tr.dep[next] <= t) { if (tr.arr[next] > t) Activate(next); next++; }
            }
            else
            {
                while (next < n && tr.dep[next] <= t) { if (tr.arr[next] > t) Activate(next); next++; }
            }
            lastT = t;

            if (!Mathf.Approximately(simSpeed, lastSpeed))
            {
                lastSpeed = simSpeed;
                float tt = Mathf.Clamp(trailSimSeconds / Mathf.Max(simSpeed, 1f), 0.05f, 3f);
                foreach (var b in pool) b.trail.time = tt;
            }

            float size = Mathf.Clamp((cam ? Mathf.Abs(cam.transform.position.y) : 3000f) * 0.004f, minSize, maxSize);
            toRemove.Clear();
            foreach (var kv in active)
            {
                int i = kv.Key;
                if (tr.arr[i] <= t) { toRemove.Add(i); continue; }
                float f = (t - tr.dep[i]) / Mathf.Max(tr.arr[i] - tr.dep[i], 1);
                // lagodny start i hamowanie
                f = Mathf.SmoothStep(0f, 1f, f);
                var p = RouteOf(i).Sample(f, out _);
                var go = kv.Value.go;
                go.transform.position = new Vector3(p.x, size * 0.6f + 2f, p.y);
                go.transform.localScale = Vector3.one * size;
                kv.Value.trail.widthMultiplier = size * 0.7f;
            }
            foreach (var i in toRemove) { Release(active[i]); active.Remove(i); }
        }

        void Activate(int i)
        {
            var b = Get();
            b.trip = i;
            bool e = data.Day.trips.ebike[i] == 1;
            b.r.sharedMaterial = e ? ebikeMat : bikeMat;
            var c = e ? Mats.EBike : Mats.Bike;
            b.trail.startColor = new Color(c.r, c.g, c.b, 0.85f);
            b.trail.endColor = new Color(c.r, c.g, c.b, 0f);
            var p = RouteOf(i).Sample(0f, out _);
            b.go.transform.position = new Vector3(p.x, 6f, p.y);
            b.trail.Clear();
            b.trail.emitting = showTrails;
            b.go.SetActive(true);
            active[i] = b;
        }

        Bike Get()
        {
            foreach (var b in pool) if (!b.go.activeSelf) return b;
            var go = new GameObject("Bike");
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            var trail = go.AddComponent<TrailRenderer>();
            trail.sharedMaterial = trailMat;
            trail.time = Mathf.Clamp(trailSimSeconds / Mathf.Max(lastSpeed, 1f), 0.05f, 3f);
            trail.minVertexDistance = 8f;
            trail.shadowCastingMode = ShadowCastingMode.Off;
            trail.alignment = LineAlignment.View;
            var bike = new Bike { go = go, r = r, trail = trail };
            pool.Add(bike);
            return bike;
        }

        void Release(Bike b)
        {
            b.trip = -1;
            b.trail.Clear();
            b.go.SetActive(false);
        }

        public void SetTrails(bool on)
        {
            showTrails = on;
            foreach (var b in active.Values) { b.trail.emitting = on; if (!on) b.trail.Clear(); }
        }
    }
}
