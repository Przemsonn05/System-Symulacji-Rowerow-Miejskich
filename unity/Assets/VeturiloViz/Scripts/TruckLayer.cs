// Ciezarowki operatora: relokacje (>= 4 rowery przewiezione razem) jako modele 3D jadace po ulicach.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class TruckLayer : MonoBehaviour
    {
        public float scale = 3.5f;   // powiekszenie modelu, zeby byl widoczny z wysokosci miasta

        class Truck { public GameObject go; public TextMesh label; public TrailRenderer trail; }
        class Pulse { public Transform t; public MeshRenderer r; public float start; }

        DataStore data;
        readonly List<Truck> pool = new List<Truck>();
        readonly Dictionary<int, Truck> active = new Dictionary<int, Truck>();
        readonly List<int> remove = new List<int>();
        readonly List<Pulse> pulses = new List<Pulse>();
        Material body, cab, stripe, trailMat, pulseMat;
        Mesh ringMesh;
        float lastT = -1;
        Camera cam;

        public int ActiveCount => active.Count;
        public int DoneCount { get; private set; }
        public int BikesMovedToday { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            body = Mats.Lit(new Color(0.92f, 0.93f, 0.95f), 0.5f);
            cab = Mats.Lit(new Color(0.15f, 0.16f, 0.18f), 0.7f);
            stripe = Mats.Unlit(Mats.Truck);
            trailMat = Mats.Vertex(Color.white);
            pulseMat = Mats.Vertex(Color.white);
            ringMesh = Ring();
        }

        public void OnDayLoaded()
        {
            foreach (var t in active.Values) t.go.SetActive(false);
            active.Clear();
            lastT = -1;
        }

        public void UpdateAt(float t)
        {
            var tr = data.Day.trucks;
            if (tr?.dep == null) return;
            bool rebuild = t < lastT || t - lastT > 900f;
            if (rebuild) { foreach (var x in active.Values) x.go.SetActive(false); active.Clear(); }

            int done = 0, moved = 0;
            for (int i = 0; i < tr.dep.Length; i++)
            {
                if (tr.dep[i] > t) break;
                bool running = tr.arr[i] > t;
                if (!running)
                {
                    done++; moved += tr.n[i];
                    if (active.TryGetValue(i, out var fin))
                    {
                        fin.go.SetActive(false);
                        active.Remove(i);
                        if (!rebuild) SpawnPulse(tr.toSt[i]);
                    }
                    continue;
                }
                if (!active.ContainsKey(i)) Activate(i);
            }
            DoneCount = done; BikesMovedToday = moved;

            remove.Clear();
            foreach (var kv in active)
            {
                int i = kv.Key;
                var route = RouteOf(i);
                float f = Mathf.SmoothStep(0, 1, (t - tr.dep[i]) / Mathf.Max(tr.arr[i] - tr.dep[i], 1));
                var p = route.Sample(f, out var dir);
                var go = kv.Value.go;
                go.transform.position = new Vector3(p.x, 0, p.y);
                if (dir.sqrMagnitude > 0.001f)
                    go.transform.rotation = Quaternion.Slerp(go.transform.rotation,
                        Quaternion.LookRotation(new Vector3(dir.x, 0, dir.y)), 0.25f);
                // etykieta zawsze przodem do kamery
                if (cam)
                {
                    var lt = kv.Value.label.transform;
                    lt.rotation = cam.transform.rotation;
                    lt.localScale = Vector3.one * Mathf.Clamp(Vector3.Distance(cam.transform.position, lt.position) * 0.03f, 2f, 600f);
                }
            }
            lastT = t;
            UpdatePulses();
        }

        Route RouteOf(int i)
        {
            int r = data.Day.trucks.route[i];
            return r >= 0 && r < data.TruckRoutes.Length ? data.TruckRoutes[r] : data.TruckRoutes.Length > 0 ? data.TruckRoutes[0] : null;
        }

        void Activate(int i)
        {
            Truck tk = null;
            foreach (var p in pool) if (!p.go.activeSelf) { tk = p; break; }
            if (tk == null) { tk = Create(); pool.Add(tk); }
            tk.label.text = "+" + data.Day.trucks.n[i];
            var r = RouteOf(i).Sample(0, out var dir);
            tk.go.transform.position = new Vector3(r.x, 0, r.y);
            if (dir.sqrMagnitude > 0.001f) tk.go.transform.rotation = Quaternion.LookRotation(new Vector3(dir.x, 0, dir.y));
            tk.trail.Clear();
            tk.go.SetActive(true);
            active[i] = tk;
        }

        Truck Create()
        {
            var root = new GameObject("Truck");
            root.transform.SetParent(transform, false);
            float s = scale;
            Part(root.transform, body, new Vector3(0, 2.0f, -1.2f) * s, new Vector3(2.4f, 2.8f, 5.6f) * s);   // skrzynia
            Part(root.transform, cab, new Vector3(0, 1.5f, 2.6f) * s, new Vector3(2.3f, 2.2f, 1.8f) * s);     // kabina
            Part(root.transform, stripe, new Vector3(0, 2.2f, -1.2f) * s, new Vector3(2.45f, 0.5f, 5.65f) * s); // pas
            Part(root.transform, stripe, new Vector3(0, 3.55f, 2.0f) * s, new Vector3(1.2f, 0.25f, 0.4f) * s); // kogut

            var labelGo = new GameObject("Label");
            labelGo.transform.SetParent(root.transform, false);
            labelGo.transform.localPosition = new Vector3(0, 6f * s, 0);
            var tm = labelGo.AddComponent<TextMesh>();
            tm.font = Ui.DefaultFont;
            tm.fontSize = 64;
            tm.characterSize = 0.1f;   // skalowane z odlegloscia kamery w UpdateAt
            tm.anchor = TextAnchor.LowerCenter;
            tm.color = Mats.Truck;
            labelGo.GetComponent<MeshRenderer>().sharedMaterial = Ui.DefaultFont.material;

            var trail = root.AddComponent<TrailRenderer>();
            trail.sharedMaterial = trailMat;
            trail.time = 1.2f;
            trail.widthMultiplier = 3f * s;
            trail.startColor = new Color(Mats.Truck.r, Mats.Truck.g, Mats.Truck.b, 0.8f);
            trail.endColor = new Color(Mats.Truck.r, Mats.Truck.g, Mats.Truck.b, 0f);
            trail.minVertexDistance = 10f;
            trail.shadowCastingMode = ShadowCastingMode.Off;
            return new Truck { go = root, label = tm, trail = trail };
        }

        static void Part(Transform parent, Material m, Vector3 pos, Vector3 size)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Destroy(g.GetComponent<Collider>());
            g.transform.SetParent(parent, false);
            g.transform.localPosition = pos;
            g.transform.localScale = size;
            g.GetComponent<MeshRenderer>().sharedMaterial = m;
        }

        // ------------------------------------------------- "fala" po dostarczeniu rowerow

        void SpawnPulse(int station)
        {
            if (station < 0 || station >= data.Stations.Length) return;
            Pulse p = null;
            foreach (var x in pulses) if (!x.t.gameObject.activeSelf) { p = x; break; }
            if (p == null)
            {
                var g = new GameObject("DeliveryPulse");
                g.transform.SetParent(transform, false);
                g.AddComponent<MeshFilter>().sharedMesh = ringMesh;
                var r = g.AddComponent<MeshRenderer>();
                r.sharedMaterial = pulseMat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                p = new Pulse { t = g.transform, r = r };
                pulses.Add(p);
            }
            var s = data.Stations[station];
            p.t.position = new Vector3(s.x, 3f, s.z);
            p.start = Time.unscaledTime;
            p.t.gameObject.SetActive(true);
        }

        void UpdatePulses()
        {
            var mpb = new MaterialPropertyBlock();
            foreach (var p in pulses)
            {
                if (!p.t.gameObject.activeSelf) continue;
                float a = (Time.unscaledTime - p.start) / 1.6f;
                if (a >= 1) { p.t.gameObject.SetActive(false); continue; }
                float r = Mathf.Lerp(40f, 260f, a);
                p.t.localScale = new Vector3(r, 1, r);
                var c = Mats.Truck; c.a = 1 - a;
                mpb.SetColor("_Color", c);
                p.r.SetPropertyBlock(mpb);
            }
        }

        static Mesh Ring()
        {
            var v = new List<Vector3>(); var t = new List<int>(); var c = new List<Color>();
            const int seg = 48;
            for (int i = 0; i <= seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(d); v.Add(d * 0.9f); c.Add(Color.white); c.Add(Color.white);
                if (i < seg)
                {
                    int s = i * 2;
                    t.Add(s); t.Add(s + 1); t.Add(s + 2); t.Add(s + 1); t.Add(s + 3); t.Add(s + 2);
                    t.Add(s); t.Add(s + 2); t.Add(s + 1); t.Add(s + 1); t.Add(s + 2); t.Add(s + 3);
                }
            }
            var m = new Mesh();
            m.SetVertices(v); m.SetColors(c); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }
}
