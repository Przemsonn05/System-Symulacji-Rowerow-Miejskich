// Geometria miasta: podloze, Wisla i woda, zielen, glowne ulice i tory (OSM), granica Warszawy,
// budynki 3D Srodmiescia (obrys OSM wyciagniety na wysokosc, okna swiecace noca), drogi rowerowe,
// POI z opisami, warstwa mieszkancow (heksagony).
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
        // Wysokosci warstw plaskich - odstepy wystarczajace przy kamerze z daleka (near plane rosnie z odlegloscia)
        const float YGreen = 0.8f, YWater = 1.6f, YPop = 2.4f, YRail = 3.0f, YRoads = 3.4f, YCycle = 4.2f, YBoundary = 5f;

        public GameObject Buildings, Cycleways, Ground, Pois, Basemap, Population, Roads;
        public readonly List<(Transform t, string category)> PoiLabels = new List<(Transform, string)>();
        readonly List<Material> facades = new List<Material>();
        Material roadMat, boundaryMat;

        public void Build(DataStore data, Transform parent)
        {
            Ground = BuildGround(parent);
            Basemap = BuildBasemap(data.Basemap, parent);
            Population = BuildPopulation(data.Basemap, parent);
            Population.SetActive(false);
            Buildings = BuildBuildings(data.City.buildings, parent);
            Cycleways = BuildCycleways(data.City.cycleways, parent);
            Pois = BuildPois(data.City.pois, parent);
        }

        /// Pora dnia: okna i latarnie swieca wieczorem (night01: 0 dzien .. 1 noc).
        public void SetNight(float night01)
        {
            var emission = new Color(1f, 0.95f, 0.85f) * (night01 * 1.6f);
            foreach (var m in facades)
                if (m.HasProperty("_EmissionColor")) m.SetColor("_EmissionColor", emission);
            if (roadMat != null)
            {
                var day = new Color(0.50f, 0.52f, 0.57f, 0.55f);
                var night = new Color(1.00f, 0.66f, 0.30f, 0.95f);
                roadMat.color = Color.Lerp(day, night, night01);
            }
            if (boundaryMat != null) boundaryMat.color = Color.Lerp(new Color(1f, 0.8f, 0.2f, 0.45f), new Color(1f, 0.8f, 0.2f, 0.7f), night01);
        }

        GameObject BuildGround(Transform parent)
        {
            var g = GameObject.CreatePrimitive(PrimitiveType.Plane);
            g.name = "Ground";
            Object.Destroy(g.GetComponent<Collider>());
            g.transform.SetParent(parent, false);
            g.transform.localScale = new Vector3(8000, 1, 8000); // 80 x 80 km
            var mr = g.GetComponent<MeshRenderer>();
            mr.sharedMaterial = Mats.Lit(Mats.Ground, 0.05f);
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = true;

            // delikatna siatka co 1 km - daje skale przy oddalonej kamerze
            var grid = new GameObject("Grid1km");
            grid.transform.SetParent(g.transform.parent, false);
            var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
            var gc = new Color(1, 1, 1, 0.025f);
            for (int k = -20; k <= 20; k++)
            {
                AddQuadLine(verts, cols, tris, new Vector2(k * 1000, -20000), new Vector2(k * 1000, 20000), 6f, 0.2f, gc);
                AddQuadLine(verts, cols, tris, new Vector2(-20000, k * 1000), new Vector2(20000, k * 1000), 6f, 0.2f, gc);
            }
            AddMesh(grid, verts, cols, tris, Queue(Mats.Vertex(Color.white), 2990));
            return g;
        }

        // ---------------------------------------------------------------- podklad

        GameObject BuildBasemap(BasemapFile bm, Transform parent)
        {
            var root = new GameObject("Basemap");
            root.transform.SetParent(parent, false);
            if (bm == null) return root;

            FlatMesh(root.transform, "Green", bm.green, YGreen, Mats.Lit(Mats.Green, 0.1f));
            var water = FlatMesh(root.transform, "Water", bm.water, YWater, Mats.Lit(Mats.Water, 0.88f));
            if (water != null) water.GetComponent<MeshRenderer>().receiveShadows = true;

            // ulice: szerokosc i jasnosc wg klasy; kolor (dzien szary / noc jak latarnie) z materialu
            Roads = new GameObject("Roads");
            Roads.transform.SetParent(root.transform, false);
            if (bm.roads != null)
            {
                float[] width = { 24f, 17f, 12f, 8f };
                float[] bright = { 1f, 0.85f, 0.62f, 0.42f };
                var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
                foreach (var r in bm.roads)
                {
                    if (r.p == null) continue;
                    int k = Mathf.Clamp(r.k, 0, 3);
                    var c = new Color(bright[k], bright[k], bright[k], 1f);
                    for (int i = 0; i + 3 < r.p.Length; i += 2)
                        AddQuadLine(verts, cols, tris, new Vector2(r.p[i], r.p[i + 1]), new Vector2(r.p[i + 2], r.p[i + 3]), width[k], YRoads, c);
                }
                roadMat = Queue(Mats.Vertex(Color.white), 3001);
                AddMesh(Roads, verts, cols, tris, roadMat);
            }
            if (bm.rail != null)
            {
                var go = new GameObject("Rail");
                go.transform.SetParent(root.transform, false);
                var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
                var c = new Color(0.62f, 0.55f, 0.70f, 0.45f);
                foreach (var r in bm.rail)
                    for (int i = 0; r.p != null && i + 3 < r.p.Length; i += 2)
                        AddQuadLine(verts, cols, tris, new Vector2(r.p[i], r.p[i + 1]), new Vector2(r.p[i + 2], r.p[i + 3]), 7f, YRail, c);
                AddMesh(go, verts, cols, tris, Queue(Mats.Vertex(Color.white), 3000));
            }
            if (bm.boundary != null)
            {
                var go = new GameObject("Boundary");
                go.transform.SetParent(root.transform, false);
                var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
                foreach (var r in bm.boundary)
                    for (int i = 0; r.p != null && i + 3 < r.p.Length; i += 2)
                        AddQuadLine(verts, cols, tris, new Vector2(r.p[i], r.p[i + 1]), new Vector2(r.p[i + 2], r.p[i + 3]), 40f, YBoundary, Color.white);
                boundaryMat = Queue(Mats.Vertex(Color.white), 3004);
                AddMesh(go, verts, cols, tris, boundaryMat);
            }
            return root;
        }

        static GameObject FlatMesh(Transform parent, string name, MeshData d, float y, Material m)
        {
            if (d?.v == null || d.t == null || d.t.Length < 3) return null;
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var v = new Vector3[d.v.Length / 2];
            for (int i = 0; i < v.Length; i++) v[i] = new Vector3(d.v[2 * i], y, d.v[2 * i + 1]);
            // trojkaty z eksportu maja rozna orientacje - ustawiamy wszystkie normalna do gory
            var t = new int[d.t.Length];
            for (int i = 0; i + 2 < d.t.Length; i += 3)
            {
                Vector3 a = v[d.t[i]], b = v[d.t[i + 1]], c = v[d.t[i + 2]];
                bool up = Vector3.Cross(b - a, c - a).y > 0;
                t[i] = d.t[i]; t[i + 1] = up ? d.t[i + 1] : d.t[i + 2]; t[i + 2] = up ? d.t[i + 2] : d.t[i + 1];
            }
            var n = new Vector3[v.Length];
            for (int i = 0; i < n.Length; i++) n[i] = Vector3.up;
            var mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.vertices = v; mesh.normals = n; mesh.triangles = t;
            mesh.RecalculateBounds();
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = m;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            return go;
        }

        GameObject BuildPopulation(BasemapFile bm, Transform parent)
        {
            var go = new GameObject("Population");
            go.transform.SetParent(parent, false);
            if (bm?.population == null) return go;
            // heksagon H3 rozdzielczosci 8 (~0,74 km2, promien ~530 m); lekko pomniejszony - widoczne granice
            const float r = 400f;
            var verts = new List<Vector3>(); var cols = new List<Color>(); var tris = new List<int>();
            foreach (var h in bm.population)
            {
                if (h.pop < 50) continue;
                var c = Mats.PopulationColor(h.pop); c.a = 0.42f;
                int s = verts.Count;
                verts.Add(new Vector3(h.x, YPop, h.z)); cols.Add(c);
                for (int k = 0; k < 6; k++)
                {
                    float a = Mathf.Deg2Rad * (60 * k + 30);
                    verts.Add(new Vector3(h.x + r * Mathf.Cos(a), YPop, h.z + r * Mathf.Sin(a)));
                    cols.Add(c);
                }
                for (int k = 0; k < 6; k++) { tris.Add(s); tris.Add(s + 1 + (k + 1) % 6); tris.Add(s + 1 + k); }
            }
            AddMesh(go, verts, cols, tris, Queue(Mats.Vertex(Color.white), 2995));
            return go;
        }

        // ---------------------------------------------------------------- budynki

        GameObject BuildBuildings(Building[] list, Transform parent)
        {
            var root = new GameObject("Buildings");
            root.transform.SetParent(parent, false);
            if (list == null) return root;

            // trzy klasy wysokosci = trzy odcienie (kamienice cieplejsze, biurowce chlodniejsze, wiezowce szklane)
            var classes = new[]
            {
                (max: 20f, color: new Color(0.80f, 0.76f, 0.70f), roof: new Color(0.36f, 0.33f, 0.31f)),
                (max: 60f, color: new Color(0.72f, 0.74f, 0.78f), roof: new Color(0.33f, 0.35f, 0.38f)),
                (max: 9999f, color: new Color(0.62f, 0.74f, 0.90f), roof: new Color(0.30f, 0.36f, 0.44f)),
            };
            var parts = new MeshParts[3];
            for (int c = 0; c < 3; c++) parts[c] = new MeshParts();

            var poly = new List<Vector2>();
            foreach (var b in list)
            {
                if (b.p == null || b.p.Length < 6) continue;
                poly.Clear();
                for (int i = 0; i + 1 < b.p.Length; i += 2) poly.Add(new Vector2(b.p[i], b.p[i + 1]));
                if (Triangulator.SignedArea(poly) < 0) poly.Reverse();
                int c = b.h <= classes[0].max ? 0 : b.h <= classes[1].max ? 1 : 2;
                Extrude(poly, b.h, parts[c]);
            }
            for (int c = 0; c < 3; c++)
            {
                var go = new GameObject("Buildings_" + c);
                go.transform.SetParent(root.transform, false);
                var p = parts[c];
                var mesh = new Mesh { indexFormat = IndexFormat.UInt32, subMeshCount = 2 };
                mesh.SetVertices(p.v); mesh.SetNormals(p.n); mesh.SetUVs(0, p.uv);
                mesh.SetTriangles(p.walls, 0); mesh.SetTriangles(p.roofs, 1);
                mesh.RecalculateBounds();
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr = go.AddComponent<MeshRenderer>();
                var facade = Mats.Facade(classes[c].color, Mats.FacadeTexture, Mats.WindowsTexture);
                facades.Add(facade);
                mr.sharedMaterials = new[] { facade, Mats.Lit(classes[c].roof, c == 2 ? 0.5f : 0.1f) };
                mr.shadowCastingMode = ShadowCastingMode.On;
            }
            return root;
        }

        class MeshParts
        {
            public readonly List<Vector3> v = new List<Vector3>(), n = new List<Vector3>();
            public readonly List<Vector2> uv = new List<Vector2>();
            public readonly List<int> walls = new List<int>(), roofs = new List<int>();
        }

        static void Extrude(List<Vector2> poly, float h, MeshParts m)
        {
            // dach
            int start = m.v.Count;
            foreach (var p in poly) { m.v.Add(new Vector3(p.x, h, p.y)); m.n.Add(Vector3.up); m.uv.Add(Vector2.zero); }
            var tri = Triangulator.Triangulate(poly);
            // Triangulate daje CCW z gory (x,z); Unity jest lewoskretny, wiec odwracamy kolejnosc
            for (int i = 0; i < tri.Count; i += 3) { m.roofs.Add(start + tri[i]); m.roofs.Add(start + tri[i + 2]); m.roofs.Add(start + tri[i + 1]); }
            // sciany (osobne wierzcholki = ostre krawedzie); u = obwod, v = wysokosc - okna co 4 m i 3,3 m
            float u = (poly[0].x * 0.37f + poly[0].y * 0.61f) % Mats.FacadeTileU; // przesuniecie - rozne wzory okien
            for (int i = 0; i < poly.Count; i++)
            {
                Vector2 a = poly[i], b = poly[(i + 1) % poly.Count];
                Vector2 d = b - a;
                float len = d.magnitude;
                if (len < 0.1f) continue;
                var n = new Vector3(d.y, 0, -d.x).normalized; // na zewnatrz dla wielokata CCW
                int s = m.v.Count;
                float u0 = u / Mats.FacadeTileU, u1 = (u + len) / Mats.FacadeTileU, v1 = h / Mats.FacadeTileV;
                m.v.Add(new Vector3(a.x, 0, a.y)); m.v.Add(new Vector3(b.x, 0, b.y));
                m.v.Add(new Vector3(b.x, h, b.y)); m.v.Add(new Vector3(a.x, h, a.y));
                m.uv.Add(new Vector2(u0, 0)); m.uv.Add(new Vector2(u1, 0)); m.uv.Add(new Vector2(u1, v1)); m.uv.Add(new Vector2(u0, v1));
                m.n.Add(n); m.n.Add(n); m.n.Add(n); m.n.Add(n);
                m.walls.Add(s); m.walls.Add(s + 2); m.walls.Add(s + 1);
                m.walls.Add(s); m.walls.Add(s + 3); m.walls.Add(s + 2);
                u += len;
            }
        }

        // ---------------------------------------------------------------- drogi rowerowe i POI

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
                                5f, YCycle, Mats.Cycleway);
            }
            AddMesh(go, verts, cols, tris, Queue(Mats.Vertex(Color.white), 3003));
            return go;
        }

        GameObject BuildPois(Poi[] list, Transform parent)
        {
            var root = new GameObject("POI");
            root.transform.SetParent(parent, false);
            if (list == null) return root;
            var font = Ui.DefaultFont;
            var placed = new List<Vector2>();
            foreach (var p in list)
            {
                // ten sam obiekt bywa w OSM kilka razy (np. PKP i WKD obok siebie) - jeden opis na 250 m
                var pos = new Vector2(p.x, p.z);
                bool near = false;
                foreach (var q in placed) if ((q - pos).sqrMagnitude < 250f * 250f) { near = true; break; }
                if (near) continue;
                placed.Add(pos);
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

        public static Material Queue(Material m, int queue) { m.renderQueue = queue; return m; }

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
