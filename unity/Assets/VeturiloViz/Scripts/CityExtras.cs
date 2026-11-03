// Detale miasta: drzewa w parkach, lasach i na cmentarzach (GPU instancing, jesienne kolory - dane sa z pazdziernika
// i listopada) oraz latarnie wzdluz glownych ulic (swieca od zmierzchu).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class InstancedTrees : MonoBehaviour
    {
        const float Cell = 1000f;
        const int Batch = 1023;

        // jesien: zielone, oliwkowe, zlote, rdzawe korony
        static readonly (Color c, float w)[] Crowns =
        {
            (new Color(0.22f, 0.36f, 0.15f), 0.38f), (new Color(0.42f, 0.45f, 0.17f), 0.24f),
            (new Color(0.80f, 0.56f, 0.14f), 0.22f), (new Color(0.62f, 0.28f, 0.11f), 0.16f),
        };

        class CellData { public Vector2 center; public List<Matrix4x4[]>[] crowns; public List<Matrix4x4[]> trunks; }

        readonly List<CellData> cells = new List<CellData>();
        Mesh crownMesh, trunkMesh;
        Material[] crownMats;
        Material trunkMat;
        Camera cam;
        public int Count { get; private set; }

        public static InstancedTrees Create(Transform parent, int[] pts)
        {
            var go = new GameObject("Trees");
            go.transform.SetParent(parent, false);
            var t = go.AddComponent<InstancedTrees>();
            t.Build(pts);
            return t;
        }

        void Build(int[] pts)
        {
            cam = Camera.main;
            crownMesh = Ellipsoid(8, 5);
            trunkMesh = Prism(6);
            crownMats = new Material[Crowns.Length];
            for (int i = 0; i < Crowns.Length; i++) { crownMats[i] = Mats.Lit(Crowns[i].c, 0.05f); crownMats[i].enableInstancing = true; }
            trunkMat = Mats.Lit(new Color(0.28f, 0.22f, 0.17f), 0.05f);
            trunkMat.enableInstancing = true;

            var rnd = new System.Random(17);
            var byCell = new Dictionary<(int, int), (List<Matrix4x4>[] crowns, List<Matrix4x4> trunks)>();
            for (int i = 0; i + 1 < pts.Length; i += 2)
            {
                float x = pts[i], z = pts[i + 1];
                var key = (Mathf.FloorToInt(x / Cell), Mathf.FloorToInt(z / Cell));
                if (!byCell.TryGetValue(key, out var lists))
                {
                    var cl = new List<Matrix4x4>[Crowns.Length];
                    for (int k = 0; k < cl.Length; k++) cl[k] = new List<Matrix4x4>();
                    lists = (cl, new List<Matrix4x4>());
                    byCell[key] = lists;
                }
                float s = 0.75f + 0.6f * (float)rnd.NextDouble();
                float trunkH = 3.5f * s, crownR = 3.6f * s, crownH = 5.5f * s;
                var rot = Quaternion.Euler(0, (float)rnd.NextDouble() * 360f, 0);
                double r = rnd.NextDouble(); int kind = 0;
                for (float acc = 0; kind < Crowns.Length - 1; kind++) { acc += Crowns[kind].w; if (r < acc) break; }
                lists.crowns[kind].Add(Matrix4x4.TRS(new Vector3(x, trunkH + crownH * 0.45f, z), rot, new Vector3(crownR, crownH, crownR)));
                lists.trunks.Add(Matrix4x4.TRS(new Vector3(x, 0, z), rot, new Vector3(0.45f * s, trunkH + crownH * 0.2f, 0.45f * s)));
                Count++;
            }
            foreach (var kv in byCell)
            {
                var cd = new CellData
                {
                    center = new Vector2((kv.Key.Item1 + 0.5f) * Cell, (kv.Key.Item2 + 0.5f) * Cell),
                    crowns = new List<Matrix4x4[]>[Crowns.Length], trunks = Chunk(kv.Value.trunks),
                };
                for (int k = 0; k < Crowns.Length; k++) cd.crowns[k] = Chunk(kv.Value.crowns[k]);
                cells.Add(cd);
            }
        }

        static List<Matrix4x4[]> Chunk(List<Matrix4x4> all)
        {
            var res = new List<Matrix4x4[]>();
            for (int i = 0; i < all.Count; i += Batch) res.Add(all.GetRange(i, Mathf.Min(Batch, all.Count - i)).ToArray());
            return res;
        }

        void Update()
        {
            if (cam == null) cam = Camera.main;
            if (cam == null) return;
            // drzewa widac tylko z blizej - z wysokosci calego miasta i tak sa ponizej piksela (las daje kolor podloza)
            var p = cam.transform.position;
            float h = Mathf.Abs(p.y);
            if (h > 9000f) return;
            // punkt na ziemi, na ktory patrzy kamera
            var f = cam.transform.forward;
            var focus = f.y < -0.05f ? p + f * (p.y / -f.y) : p;
            float radius = Mathf.Clamp(h * 2.2f, 2500f, 9000f);
            var shadows = h < 2500f ? ShadowCastingMode.On : ShadowCastingMode.Off;
            var focus2 = new Vector2(focus.x, focus.z);
            foreach (var c in cells)
            {
                if ((c.center - focus2).sqrMagnitude > radius * radius) continue;
                for (int k = 0; k < crownMats.Length; k++)
                    foreach (var batch in c.crowns[k])
                        Graphics.DrawMeshInstanced(crownMesh, 0, crownMats[k], batch, batch.Length, null, shadows, true, gameObject.layer);
                if (h < 4000f)
                    foreach (var batch in c.trunks)
                        Graphics.DrawMeshInstanced(trunkMesh, 0, trunkMat, batch, batch.Length, null, ShadowCastingMode.Off, true, gameObject.layer);
            }
        }

        /// Elipsoida (korona) o promieniu 1 i wysokosci 1, malo trojkatow.
        static Mesh Ellipsoid(int seg, int rings)
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            for (int r = 0; r <= rings; r++)
            {
                float phi = Mathf.PI * r / rings;
                for (int s = 0; s <= seg; s++)
                {
                    float th = 2 * Mathf.PI * s / seg;
                    var d = new Vector3(Mathf.Sin(phi) * Mathf.Cos(th), Mathf.Cos(phi), Mathf.Sin(phi) * Mathf.Sin(th));
                    // lekko nieregularna korona
                    float jitter = 1f + 0.12f * Mathf.Sin(th * 3 + r * 1.7f);
                    v.Add(new Vector3(d.x * jitter, d.y * 0.5f, d.z * jitter)); n.Add(d);
                }
            }
            for (int r = 0; r < rings; r++)
                for (int s = 0; s < seg; s++)
                {
                    int a = r * (seg + 1) + s, b = a + seg + 1;
                    t.Add(a); t.Add(a + 1); t.Add(b); t.Add(b); t.Add(a + 1); t.Add(b + 1);
                }
            var m = new Mesh();
            m.SetVertices(v); m.SetNormals(n); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }

        /// Pien: graniastoslup o promieniu 1 i wysokosci 1 (od y = 0).
        static Mesh Prism(int seg)
        {
            var v = new List<Vector3>(); var n = new List<Vector3>(); var t = new List<int>();
            for (int s = 0; s <= seg; s++)
            {
                float th = 2 * Mathf.PI * s / seg;
                var d = new Vector3(Mathf.Cos(th), 0, Mathf.Sin(th));
                v.Add(d); v.Add(d + Vector3.up); n.Add(d); n.Add(d);
            }
            for (int s = 0; s < seg; s++) { int a = 2 * s; t.Add(a); t.Add(a + 1); t.Add(a + 2); t.Add(a + 2); t.Add(a + 1); t.Add(a + 3); }
            var m = new Mesh();
            m.SetVertices(v); m.SetNormals(n); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }

    /// Latarnie: punkty swiatla co ok. 45 m po obu stronach glownych ulic; jasnosc od pory dnia.
    public class StreetLights : MonoBehaviour
    {
        ParticleSystem ps;
        ParticleSystemRenderer psr;
        public int Count { get; private set; }

        public static StreetLights Create(Transform parent, Road[] roads, float[] width)
        {
            var go = new GameObject("StreetLights");
            go.transform.SetParent(parent, false);
            var sl = go.AddComponent<StreetLights>();
            sl.Build(roads, width);
            return sl;
        }

        void Build(Road[] roads, float[] width)
        {
            var pts = new List<ParticleSystem.Particle>();
            var warm = new Color(1f, 0.78f, 0.45f, 0.9f);
            foreach (var r in roads)
            {
                if (r.p == null || r.k > 2) continue;
                float step = 45f, carry = 0f, side = 1f;
                float off = width[r.k] * 0.5f + 3f;
                float y = r.b == 1 ? 18f : 8f;
                for (int i = 0; i + 3 < r.p.Length; i += 2)
                {
                    var a = new Vector2(r.p[i], r.p[i + 1]); var b = new Vector2(r.p[i + 2], r.p[i + 3]);
                    float len = Vector2.Distance(a, b);
                    if (len < 0.1f) continue;
                    var dir = (b - a) / len; var nrm = new Vector2(-dir.y, dir.x);
                    for (float d = carry; d < len; d += step)
                    {
                        var q = a + dir * d + nrm * off * side;
                        side = -side;
                        pts.Add(new ParticleSystem.Particle
                        {
                            position = new Vector3(q.x, y, q.y), startSize = 26f, startColor = warm,
                            remainingLifetime = 1e6f, startLifetime = 1e6f,
                        });
                        if (pts.Count >= 60000) break;
                    }
                    carry = (carry - len) % step; if (carry < 0) carry += step;
                }
            }
            Count = pts.Count;
            ps = Fx.GlowSystem(transform, "Lamps", Mathf.Max(Count, 1), 3100);
            psr = ps.GetComponent<ParticleSystemRenderer>();
            psr.maxParticleSize = 0.02f;
            ps.SetParticles(pts.ToArray(), Count);
            SetNight(0);
        }

        public void SetNight(float night01)
        {
            if (psr == null) return;
            psr.enabled = night01 > 0.05f;
            if (psr.enabled) Mats.SetGlowTint(psr.sharedMaterial, night01);
        }
    }
}
