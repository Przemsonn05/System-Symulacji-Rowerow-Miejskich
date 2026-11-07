// Rowery w drodze: kazdy przejazd z danych to swiecacy punkt jadacy po trasie (po drogach rowerowych,
// jesli jest graf OSM), ze sladem; rozblysk przy oddaniu roweru; rowery zostawione poza stacjami.
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
        public bool showLoose = true;

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
        ParticleSystem glow, flashes, loose;
        ParticleSystem.Particle[] glowBuf = new ParticleSystem.Particle[512], looseBuf = new ParticleSystem.Particle[128];
        int next;           // indeks pierwszego przejazdu, ktory jeszcze nie wystartowal
        float lastT = -1;
        float lastSpeed = -1;
        Camera cam;

        public int ActiveCount => active.Count;

        /// Przejazd, ktorego rower trafil promien (klikniecie), albo -1.
        public int TripOf(Collider c)
        {
            if (c == null) return -1;
            foreach (var kv in active) if (kv.Value.go == c.gameObject) return kv.Key;
            return -1;
        }

        /// Polozenie roweru danego przejazdu (false, gdy przejazd sie skonczyl albo jeszcze nie zaczal).
        public bool PositionOf(int trip, out Vector3 pos)
        {
            pos = Vector3.zero;
            if (!active.TryGetValue(trip, out var b)) return false;
            pos = b.go.transform.position;
            return true;
        }

        public Route RouteOfTrip(int trip) => RouteOf(trip);
        public int StartedCount => next;
        public int LooseCount { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            bikeMat = Mats.Unlit(Mats.Bike);
            ebikeMat = Mats.Unlit(Mats.EBike);
            trailMat = CityBuilder.Queue(Mats.Vertex(Color.white), 3020);
            var tmp = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            mesh = tmp.GetComponent<MeshFilter>().sharedMesh;
            Destroy(tmp);
            glow = Fx.GlowSystem(transform, "BikeGlow", 4000, 3101);
            flashes = Fx.FlashSystem(transform, "ArrivalFlash", 3102);
            loose = Fx.GlowSystem(transform, "LooseBikes", 1000, 3101);
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

        public void UpdateAt(float t, float simSpeed, bool playing)
        {
            var tr = data.Day.trips;
            int n = tr.dep.Length;
            // skok w tyl albo duzy skok w przod (suwak) - przebudowa listy aktywnych
            bool rebuild = t < lastT || t - lastT > 900f;
            if (rebuild)
            {
                foreach (var b in active.Values) Release(b);
                active.Clear();
                next = 0;
            }
            while (next < n && tr.dep[next] <= t) { if (tr.arr[next] > t) Activate(next); next++; }
            lastT = t;

            if (!Mathf.Approximately(simSpeed, lastSpeed))
            {
                lastSpeed = simSpeed;
                float tt = Mathf.Clamp(trailSimSeconds / Mathf.Max(simSpeed, 1f), 0.05f, 3f);
                foreach (var b in pool) b.trail.time = tt;
            }

            float camH = cam ? Mathf.Abs(cam.transform.position.y) : 3000f;
            float size = Mathf.Clamp(camH * 0.004f, minSize, maxSize);
            if (glowBuf.Length < active.Count) glowBuf = new ParticleSystem.Particle[active.Count * 2];
            int g = 0;
            toRemove.Clear();
            foreach (var kv in active)
            {
                int i = kv.Key;
                if (tr.arr[i] <= t)
                {
                    toRemove.Add(i);
                    if (playing && !rebuild) Flash(RouteOf(i).Sample(1f, out _), tr.ebike[i] == 1, size);
                    continue;
                }
                float f = (t - tr.dep[i]) / Mathf.Max(tr.arr[i] - tr.dep[i], 1);
                // lagodny start i hamowanie
                f = Mathf.SmoothStep(0f, 1f, f);
                var p = RouteOf(i).Sample(f, out _);
                var go = kv.Value.go;
                var pos = new Vector3(p.x, size * 0.6f + 8f, p.y);
                go.transform.position = pos;
                go.transform.localScale = Vector3.one * size;
                kv.Value.trail.widthMultiplier = size * 0.7f;

                var c = ColorOf(i); c.a = 0.55f;
                glowBuf[g].position = pos;
                glowBuf[g].startSize = size * 5.5f;
                glowBuf[g].startColor = c;
                glowBuf[g].remainingLifetime = 1000f;
                glowBuf[g].startLifetime = 1000f;
                g++;
            }
            foreach (var i in toRemove) { Release(active[i]); active.Remove(i); }
            glow.SetParticles(glowBuf, g);
            UpdateLoose(t, size);
        }

        /// Typ przejazdu: dane - 1 = trasa dojazdowa; symulacja - typ klienta (0 = zwykly).
        int KindOf(int i)
        {
            var k = data.Day.trips.kind;
            return k != null && i < k.Length ? k[i] : 0;
        }

        Color ColorOf(int i)
        {
            if (data.Day.trips.ebike[i] == 1) return Mats.EBike;
            int k = KindOf(i);
            return k <= 0 ? Mats.Bike : data.IsSim ? Mats.UserType(k) : Mats.Commute;
        }

        readonly Dictionary<int, Material> kindMats = new Dictionary<int, Material>();
        Material KindMat(int k)
        {
            if (!kindMats.TryGetValue(k, out var m))
                kindMats[k] = m = Mats.Unlit(data.IsSim ? Mats.UserType(k) : Mats.Commute);
            return m;
        }

        void Flash(Vector2 p, bool ebike, float size)
        {
            var e = new ParticleSystem.EmitParams
            {
                position = new Vector3(p.x, 10f, p.y),
                startSize = size * 9f,
                startColor = ebike ? new Color(0.45f, 0.9f, 1f, 0.9f) : new Color(1f, 0.9f, 0.5f, 0.9f),
                applyShapeToPosition = false,
            };
            flashes.Emit(e, 1);
        }

        void UpdateLoose(float t, float size)
        {
            var lo = data.Day.loose;
            var idx = data.LooseAt(t);
            LooseCount = idx.Count;
            if (!showLoose || lo?.x == null) { loose.SetParticles(looseBuf, 0); return; }
            if (looseBuf.Length < idx.Count) looseBuf = new ParticleSystem.Particle[idx.Count * 2];
            int g = 0;
            foreach (int i in idx)
            {
                looseBuf[g].position = new Vector3(lo.x[i], 10f, lo.z[i]);
                looseBuf[g].startSize = size * 3.2f;
                looseBuf[g].startColor = new Color(0.95f, 0.95f, 1f, 0.75f);
                looseBuf[g].remainingLifetime = 1000f;
                looseBuf[g].startLifetime = 1000f;
                g++;
            }
            loose.SetParticles(looseBuf, g);
        }

        void Activate(int i)
        {
            var b = Get();
            b.trip = i;
            bool e = data.Day.trips.ebike[i] == 1;
            var c = ColorOf(i);
            b.r.sharedMaterial = e ? ebikeMat : KindOf(i) > 0 ? KindMat(KindOf(i)) : bikeMat;
            b.trail.startColor = new Color(c.r, c.g, c.b, 0.85f);
            b.trail.endColor = new Color(c.r, c.g, c.b, 0f);
            var p = RouteOf(i).Sample(0f, out _);
            b.go.transform.position = new Vector3(p.x, 8f, p.y);
            b.trail.Clear();
            b.trail.emitting = showTrails;
            b.go.SetActive(true);
            active[i] = b;
        }

        Bike Get()
        {
            foreach (var b in pool) if (!b.go.activeSelf) return b;
            var go = new GameObject("Bike");
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            // wiekszy niz rower - latwiej kliknac
            var col = go.AddComponent<SphereCollider>();
            col.radius = 1.6f;
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
