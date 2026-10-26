// Geometria miasta: podloze, budynki 3D (obrys OSM wyciagniety na wysokosc), drogi rowerowe, POI.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public static class Triangulator
    {
        /// Triangulacja wielokata prostego metoda "ear clipping". Zwraca indeksy trojkatow (CCW patrzac z gory).
        public static List<int> Triangulate(IList<Vector2> poly)
        {
            var result = new List<int>();
            int n = poly.Count;
            if (n < 3) return result;
            var idx = new List<int>(n);
            if (SignedArea(poly) > 0) for (int i = 0; i < n; i++) idx.Add(i);
            else for (int i = n - 1; i >= 0; i--) idx.Add(i);

            int guard = 0;
            while (idx.Count > 3 && guard++ < 5000)
            {
                bool cut = false;
                for (int i = 0; i < idx.Count; i++)
                {
                    int a = idx[(i + idx.Count - 1) % idx.Count], b = idx[i], c = idx[(i + 1) % idx.Count];
                    if (Cross(poly[a], poly[b], poly[c]) <= 1e-6f) continue; // wierzcholek wklesly
                    bool inside = false;
                    for (int j = 0; j < idx.Count; j++)
                    {
                        int p = idx[j];
                        if (p == a || p == b || p == c) continue;
                        if (InTriangle(poly[p], poly[a], poly[b], poly[c])) { inside = true; break; }
                    }
                    if (inside) continue;
                    result.Add(a); result.Add(b); result.Add(c);
                    idx.RemoveAt(i);
                    cut = true;
                    break;
                }
                if (!cut) break; // wielokat zdegenerowany - reszta wachlarzem
            }
            for (int i = 1; i + 1 < idx.Count; i++) { result.Add(idx[0]); result.Add(idx[i]); result.Add(idx[i + 1]); }
            return result;
        }

        public static float SignedArea(IList<Vector2> p)
        {
            float s = 0;
            for (int i = 0, j = p.Count - 1; i < p.Count; j = i++) s += (p[j].x * p[i].y - p[i].x * p[j].y);
            return s * 0.5f;
        }

        static float Cross(Vector2 a, Vector2 b, Vector2 c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);

        static bool InTriangle(Vector2 p, Vector2 a, Vector2 b, Vector2 c)
        {
            float d1 = Cross(a, b, p), d2 = Cross(b, c, p), d3 = Cross(c, a, p);
            bool neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
            return !(neg && pos);
        }
    }

    public class CityBuilder
    {
        public GameObject Buildings, Cycleways, Ground, Pois;
        public readonly List<(Transform t, string category)> PoiLabels = new List<(Transform, string)>();

        public void Build(DataStore data, Transform parent)
        {
            Ground = BuildGround(parent);
            Buildings = BuildBuildings(data.City.buildings, parent);
            Cycleways = BuildCycleways(data.City.cycleways, parent);
            Pois = BuildPois(data.City.pois, parent);
        }

        GameObject BuildGround(Transform parent)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Plane);
            g.name = "Ground";
            Object.Destroy(g.GetComponent<Collider>());
            g.transform.SetParent(parent, false);
            g.transform.localScale = new Vector3(6000, 1, 6000); // 60 x 60 km
            g.GetComponent<MeshRenderer>().sharedMaterial = Mats.Lit(Mats.Ground, 0.05f);
            g.GetComponent<MeshRenderer>().shadowCastingMode = ShadowCastingMode.Off;

            // delikatna siatka co 1 km - daje skale przy oddalonej kamerze
            var grid = new GameObject("Grid1km");
            grid.transform.SetParent(parent, false);
            var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
            var gc = new Color(1, 1, 1, 0.035f);
            for (int k = -15; k <= 15; k++)
            {
                AddQuadLine(verts, cols, tris, new Vector2(k * 1000, -15000), new Vector2(k * 1000, 15000), 6f, 0.15f, gc);
                AddQuadLine(verts, cols, tris, new Vector2(-15000, k * 1000), new Vector2(15000, k * 1000), 6f, 0.15f, gc);
            }
            AddMesh(grid, verts, cols, tris, Mats.Vertex(Color.white));
            return g;
        }

        GameObject BuildBuildings(Building[] list, Transform parent)
        {
            var root = new GameObject("Buildings");
            root.transform.SetParent(parent, false);
            if (list == null) return root;

            // trzy klasy wysokosci = trzy odcienie (szklane wiezowce jasniejsze)
            var classes = new[]
            {
                (max: 20f, color: new Color(0.42f, 0.44f, 0.48f)),
                (max: 60f, color: new Color(0.52f, 0.55f, 0.60f)),
                (max: 9999f, color: new Color(0.62f, 0.70f, 0.80f)),
            };
            var meshes = new List<Vector3>[3]; var normals = new List<Vector3>[3]; var tris = new List<int>[3];
            for (int c = 0; c < 3; c++) { meshes[c] = new List<Vector3>(); normals[c] = new List<Vector3>(); tris[c] = new List<int>(); }

            var poly = new List<Vector2>();
            foreach (var b in list)
            {
                if (b.p == null || b.p.Length < 6) continue;
                poly.Clear();
                for (int i = 0; i + 1 < b.p.Length; i += 2) poly.Add(new Vector2(b.p[i], b.p[i + 1]));
                if (Triangulator.SignedArea(poly) < 0) poly.Reverse();
                int c = b.h <= classes[0].max ? 0 : b.h <= classes[1].max ? 1 : 2;
                Extrude(poly, b.h, meshes[c], normals[c], tris[c]);
            }
            for (int c = 0; c < 3; c++)
            {
                var go = new GameObject("Buildings_" + c);
                go.transform.SetParent(root.transform, false);
                var mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
                mesh.SetVertices(meshes[c]); mesh.SetNormals(normals[c]); mesh.SetTriangles(tris[c], 0);
                mesh.RecalculateBounds();
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = Mats.Lit(classes[c].color, c == 2 ? 0.6f : 0.15f);
                mr.shadowCastingMode = ShadowCastingMode.On;
            }
            return root;
        }

        static void Extrude(List<Vector2> poly, float h, List<Vector3> v, List<Vector3> nrm, List<int> t)
        {
            // dach
            int start = v.Count;
            foreach (var p in poly) { v.Add(new Vector3(p.x, h, p.y)); nrm.Add(Vector3.up); }
            var tri = Triangulator.Triangulate(poly);
            // Triangulate daje CCW z gory (x,z); Unity jest lewoskretny, wiec odwracamy kolejnosc
            for (int i = 0; i < tri.Count; i += 3) { t.Add(start + tri[i]); t.Add(start + tri[i + 2]); t.Add(start + tri[i + 1]); }
            // sciany (osobne wierzcholki = ostre krawedzie)
            for (int i = 0; i < poly.Count; i++)
            {
                Vector2 a = poly[i], b = poly[(i + 1) % poly.Count];
                Vector2 d = b - a;
                if (d.sqrMagnitude < 0.01f) continue;
                var n = new Vector3(d.y, 0, -d.x).normalized; // na zewnatrz dla wielokata CCW
                int s = v.Count;
                v.Add(new Vector3(a.x, 0, a.y)); v.Add(new Vector3(b.x, 0, b.y));
                v.Add(new Vector3(b.x, h, b.y)); v.Add(new Vector3(a.x, h, a.y));
                nrm.Add(n); nrm.Add(n); nrm.Add(n); nrm.Add(n);
                t.Add(s); t.Add(s + 2); t.Add(s + 1);
                t.Add(s); t.Add(s + 3); t.Add(s + 2);
            }
        }

        GameObject BuildCycleways(Polyline[] list, Transform parent)
        {
            var go = new GameObject("Cycleways");
            go.transform.SetParent(parent, false);
            if (list == null) return go;
            var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
            foreach (var l in list)
            {
                if (l.p == null) continue;
                for (int i = 0; i + 3 < l.p.Length; i += 2)
                    AddQuadLine(verts, cols, tris, new Vector2(l.p[i], l.p[i + 1]), new Vector2(l.p[i + 2], l.p[i + 3]),
                                5f, 0.6f, Mats.Cycleway);
            }
            AddMesh(go, verts, cols, tris, Mats.Vertex(Color.white));
            return go;
        }

        GameObject BuildPois(Poi[] list, Transform parent)
        {
            var root = new GameObject("POI");
            root.transform.SetParent(parent, false);
            if (list == null) return root;
            var font = Ui.DefaultFont;
            foreach (var p in list)
            {
                Color c; string prefix;
                switch (p.c)
                {
                    case "metro": c = new Color(1f, 0.35f, 0.35f); prefix = "M "; break;
                    case "train_station": c = new Color(0.9f, 0.9f, 0.9f); prefix = "PKP "; break;
                    case "university": c = new Color(0.75f, 0.6f, 1f); prefix = ""; break;
                    case "mall": c = new Color(1f, 0.8f, 0.5f); prefix = ""; break;
                    default: c = new Color(0.7f, 0.9f, 1f); prefix = ""; break;
                }
                var go = new GameObject("POI_" + p.c);
                go.transform.SetParent(root.transform, false);
                go.transform.position = new Vector3(p.x, 60f, p.z);
                var tm = go.AddComponent<TextMesh>();
                tm.text = prefix + (string.IsNullOrEmpty(p.n) ? p.c : p.n);
                tm.font = font;
                tm.fontSize = 64;
                tm.characterSize = 0.1f;   // ok. 0,64 m wysokosci; skalowane z odlegloscia w VeturiloApp
                tm.anchor = TextAnchor.LowerCenter;
                tm.color = c;
                go.GetComponent<MeshRenderer>().sharedMaterial = font.material;
                PoiLabels.Add((go.transform, p.c));
            }
            return root;
        }

        // ---------------------------------------------------------------- pomocnicze

        public static void AddQuadLine(List<Vector3> v, List<Color> c, List<int> t, Vector2 a, Vector2 b, float width,
                                       float y, Color color)
        {
            Vector2 d = b - a;
            if (d.sqrMagnitude < 0.01f) return;
            Vector2 n = new Vector2(-d.y, d.x).normalized * (width * 0.5f);
            int s = v.Count;
            v.Add(new Vector3(a.x + n.x, y, a.y + n.y)); v.Add(new Vector3(a.x - n.x, y, a.y - n.y));
            v.Add(new Vector3(b.x - n.x, y, b.y - n.y)); v.Add(new Vector3(b.x + n.x, y, b.y + n.y));
            c.Add(color); c.Add(color); c.Add(color); c.Add(color);
            // obie strony - linia widoczna niezaleznie od orientacji
            t.Add(s); t.Add(s + 1); t.Add(s + 2); t.Add(s); t.Add(s + 2); t.Add(s + 3);
            t.Add(s); t.Add(s + 2); t.Add(s + 1); t.Add(s); t.Add(s + 3); t.Add(s + 2);
        }

        public static void AddMesh(GameObject go, List<Vector3> v, List<Color> c, List<int> t, Material m)
        {
            var mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.SetVertices(v); mesh.SetColors(c); mesh.SetTriangles(t, 0);
            mesh.RecalculateBounds();
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = m;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
        }
    }
}
