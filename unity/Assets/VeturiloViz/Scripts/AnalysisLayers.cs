// Warstwy analityczne:
//  - DayTrailLayer: slady wszystkich przejazdow dnia narastajace z czasem - pod wieczor widac glowne korytarze rowerowe,
//  - LostDemandLayer: szacowany utracony popyt (klienci przy pustej stacji) jako heksagony rosnace w gore.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class DayTrailLayer : MonoBehaviour
    {
        DataStore data;
        Material mat;
        Mesh mesh;
        MeshFilter mf;
        bool dirty = true;

        public void Init(DataStore d)
        {
            data = d;
            mat = Mats.DayTrails();
            mat.SetFloat("_Width", 2.2f);
            mat.SetColor("_Color", new Color(1f, 1f, 1f, 0.035f));
            mf = gameObject.AddComponent<MeshFilter>();
            var mr = gameObject.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
        }

        public void OnDayLoaded() => dirty = true;

        public void UpdateAt(float t)
        {
            if (!gameObject.activeSelf) return;
            if (dirty) Rebuild();
            mat.SetFloat("_TimeCut", t);
        }

        void Rebuild()
        {
            dirty = false;
            var tr = data.Day.trips;
            var v = new List<Vector3>(); var n = new List<Vector3>(); var uv = new List<Vector2>(); var c = new List<Color>();
            var idx = new List<int>();
            for (int i = 0; i < tr.dep.Length; i++)
            {
                int r = tr.route[i];
                Route route = r >= 0 && r < data.BikeRoutes.Length ? data.BikeRoutes[r]
                    : new Route(new Vector2(tr.fx[i], tr.fz[i]), new Vector2(tr.tx[i], tr.tz[i]));
                if (route.length < 50f) continue;
                var col = tr.ebike[i] == 1 ? new Color(0.35f, 0.85f, 1f) : new Color(1f, 0.78f, 0.3f);
                float dur = Mathf.Max(tr.arr[i] - tr.dep[i], 1);
                for (int k = 0; k + 1 < route.pts.Length; k++)
                {
                    Vector2 a = route.pts[k], b = route.pts[k + 1];
                    Vector2 d = b - a;
                    if (d.sqrMagnitude < 0.25f) continue;
                    var nn = new Vector3(-d.y, 0, d.x).normalized;
                    float ta = tr.dep[i] + dur * route.cum[k] / route.length;
                    float tb = tr.dep[i] + dur * route.cum[k + 1] / route.length;
                    int s = v.Count;
                    v.Add(new Vector3(a.x, 6f, a.y)); v.Add(new Vector3(a.x, 6f, a.y));
                    v.Add(new Vector3(b.x, 6f, b.y)); v.Add(new Vector3(b.x, 6f, b.y));
                    n.Add(nn); n.Add(nn); n.Add(nn); n.Add(nn);
                    uv.Add(new Vector2(ta, -1)); uv.Add(new Vector2(ta, 1)); uv.Add(new Vector2(tb, -1)); uv.Add(new Vector2(tb, 1));
                    c.Add(col); c.Add(col); c.Add(col); c.Add(col);
                    idx.Add(s); idx.Add(s + 1); idx.Add(s + 2); idx.Add(s + 2); idx.Add(s + 1); idx.Add(s + 3);
                }
            }
            if (mesh == null) mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.Clear();
            mesh.SetVertices(v); mesh.SetNormals(n); mesh.SetUVs(0, uv); mesh.SetColors(c); mesh.SetTriangles(idx, 0);
            // szerokosc dodawana w shaderze - powiekszamy granice, zeby Unity nie odcinalo siatki
            var bnd = mesh.bounds; bnd.Expand(400f); mesh.bounds = bnd;
            mf.sharedMesh = mesh;
        }
    }

    public class LostDemandLayer : MonoBehaviour
    {
        public float radius = 650f;          // heksagon ~1,1 km szerokosci
        public float metersPerPerson = 28f;

        class Hex { public Vector2 center; public List<int> stations = new List<int>(); public Transform t; public MeshRenderer r; public float value; }

        DataStore data;
        readonly List<Hex> hexes = new List<Hex>();
        readonly List<TextMesh> labels = new List<TextMesh>();
        MaterialPropertyBlock mpb;
        Camera cam;
        float lastT = -1;

        public float Total { get; private set; }
        public float MaxHex { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            mpb = new MaterialPropertyBlock();
            var mesh = HexPrism();
            // wlasne swiecenie - heksagony czytelne takze noca
            var mat = Mats.Lit(Color.white, 0.25f);
            mat.EnableKeyword("_EMISSION");
            mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            var byKey = new Dictionary<(int, int), Hex>();
            for (int i = 0; i < data.Stations.Length; i++)
            {
                var key = AxialOf(data.Stations[i].x, data.Stations[i].z);
                if (!byKey.TryGetValue(key, out var h))
                {
                    h = new Hex { center = CenterOf(key) };
                    byKey[key] = h;
                    hexes.Add(h);
                }
                h.stations.Add(i);
            }
            foreach (var h in hexes)
            {
                var go = new GameObject("LostHex");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                go.transform.position = new Vector3(h.center.x, 0, h.center.y);
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                h.r = go.AddComponent<MeshRenderer>();
                h.r.sharedMaterial = mat;
                h.r.shadowCastingMode = ShadowCastingMode.On;
                h.t = go.transform;
            }
            for (int k = 0; k < 6; k++)
            {
                var holder = new GameObject("LostLabel");
                holder.layer = gameObject.layer;
                holder.transform.SetParent(transform, false);
                var tm = Fx.Label(holder.transform, "", Color.white);
                tm.gameObject.layer = gameObject.layer;
                labels.Add(tm);
            }
        }

        // heksagony "plaskie" (flat-top), wspolrzedne osiowe
        (int, int) AxialOf(float x, float z)
        {
            float q = (2f / 3f * x) / radius, r = (-1f / 3f * x + Mathf.Sqrt(3f) / 3f * z) / radius;
            float cx = q, cz = r, cy = -q - r;
            float rx = Mathf.Round(cx), ry = Mathf.Round(cy), rz = Mathf.Round(cz);
            float dx = Mathf.Abs(rx - cx), dy = Mathf.Abs(ry - cy), dz = Mathf.Abs(rz - cz);
            if (dx > dy && dx > dz) rx = -ry - rz; else if (dy <= dz) rz = -rx - ry;
            return ((int)rx, (int)rz);
        }

        Vector2 CenterOf((int q, int r) a) => new Vector2(radius * 1.5f * a.q, radius * Mathf.Sqrt(3f) * (a.r + a.q * 0.5f));

        public void OnDayLoaded() => lastT = -1;

        public void UpdateAt(float t)
        {
            if (!gameObject.activeSelf) return;
            if (Mathf.Abs(t - lastT) < 30f && lastT >= 0) { FaceLabels(); return; }
            lastT = t;
            Total = 0; MaxHex = 0;
            foreach (var h in hexes)
            {
                float v = 0;
                foreach (int s in h.stations) v += data.LostAt(s, t);
                h.value = v;
                Total += v;
                MaxHex = Mathf.Max(MaxHex, v);
                bool show = v >= 0.3f;
                if (h.r.enabled != show) h.r.enabled = show;
                if (!show) continue;
                float height = Mathf.Min(v * metersPerPerson, 1600f);
                h.t.localScale = new Vector3(radius * 0.86f, height, radius * 0.86f);
                mpb.Clear();
                var lc = LostColor(v);
                Mats.SetColor(mpb, lc);
                mpb.SetColor("_EmissionColor", lc * 0.55f);
                h.r.SetPropertyBlock(mpb);
            }
            // opisy nad szesciu najwyzszymi heksagonami
            hexes.Sort((a, b) => b.value.CompareTo(a.value));
            for (int k = 0; k < labels.Count; k++)
            {
                bool on = k < hexes.Count && hexes[k].value >= 1f;
                labels[k].transform.parent.gameObject.SetActive(on);
                if (!on) continue;
                var h = hexes[k];
                labels[k].transform.parent.position = new Vector3(h.center.x, Mathf.Min(h.value * metersPerPerson, 1600f) + 40f, h.center.y);
                labels[k].text = $"≈{h.value:0} os.";
                labels[k].color = Color.Lerp(Color.white, LostColor(h.value), 0.4f);
            }
            FaceLabels();
        }

        void FaceLabels()
        {
            if (cam == null) return;
            foreach (var l in labels)
                if (l.transform.parent.gameObject.activeSelf) Fx.Face(l.transform, cam, 0.02f, 40000f);
        }

        public static Color LostColor(float v)
        {
            var a = new Color(1f, 0.85f, 0.3f); var b = new Color(1f, 0.42f, 0.15f); var c = new Color(0.92f, 0.12f, 0.35f);
            return v < 8f ? Color.Lerp(a, b, v / 8f) : Color.Lerp(b, c, Mathf.Clamp01((v - 8f) / 22f));
        }

        /// Graniastoslup szesciokatny: promien 1, wysokosc 1, podstawa na y = 0.
        static Mesh HexPrism()
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            var ring = new Vector3[6];
            for (int k = 0; k < 6; k++) { float a = Mathf.Deg2Rad * 60 * k; ring[k] = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a)); }
            int top = v.Count;
            v.Add(Vector3.up); n.Add(Vector3.up);
            for (int k = 0; k < 6; k++) { v.Add(ring[k] + Vector3.up); n.Add(Vector3.up); }
            for (int k = 0; k < 6; k++) { t.Add(top); t.Add(top + 1 + (k + 1) % 6); t.Add(top + 1 + k); }
            for (int k = 0; k < 6; k++)
            {
                var a = ring[k]; var b = ring[(k + 1) % 6];
                var nn = ((a + b) * 0.5f).normalized;
                int s = v.Count;
                v.Add(a); v.Add(b); v.Add(b + Vector3.up); v.Add(a + Vector3.up);
                n.Add(nn); n.Add(nn); n.Add(nn); n.Add(nn);
                t.Add(s); t.Add(s + 2); t.Add(s + 1); t.Add(s); t.Add(s + 3); t.Add(s + 2);
            }
            var m = new Mesh();
            m.SetVertices(v); m.SetNormals(n); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }
}
