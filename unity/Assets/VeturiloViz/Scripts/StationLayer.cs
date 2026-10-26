// Stacje: slupek 3D (wysokosc = liczba rowerow, kolor = zapelnienie), pierscien pustej / przepelnionej stacji.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class StationView
    {
        public int Index;
        public StationInfo Info;
        public Transform Root, Column, Base, Ring;
        public MeshRenderer ColumnR, BaseR, RingR;
        public float Bikes, EBikes;
        public bool Highlight;
    }

    public class StationLayer : MonoBehaviour
    {
        public float metersPerBike = 14f;
        public float columnWidth = 42f;
        public float maxHeight = 700f;

        public readonly List<StationView> Views = new List<StationView>();
        DataStore data;
        MaterialPropertyBlock mpb;
        Material ringMat, baseMat, columnMat;
        public StationView Selected { get; set; }
        public StationView Hovered { get; set; }

        public void Build(DataStore d)
        {
            data = d;
            mpb = new MaterialPropertyBlock();
            columnMat = Mats.Unlit(Color.white);
            baseMat = Mats.Unlit(Color.white);
            ringMat = Mats.Vertex(Color.white);
            var ringMesh = RingMesh(1f, 0.82f, 48);

            for (int i = 0; i < data.Stations.Length; i++)
            {
                var s = data.Stations[i];
                var root = new GameObject("Station_" + s.id);
                root.transform.SetParent(transform, false);
                root.transform.position = new Vector3(s.x, 0, s.z);
                // jeden collider na stacje (klikniecie / najechanie)
                var col = root.AddComponent<CapsuleCollider>();
                col.radius = columnWidth * 1.2f; col.height = 400f; col.center = new Vector3(0, 200f, 0);

                var v = new StationView { Index = i, Info = s, Root = root.transform };
                v.Base = Prim(PrimitiveType.Cylinder, root.transform, "Base", baseMat, out v.BaseR);
                v.Base.localScale = new Vector3(columnWidth * 1.6f, 1.5f, columnWidth * 1.6f);
                v.Base.localPosition = new Vector3(0, 1.5f, 0);

                v.Column = Prim(PrimitiveType.Cube, root.transform, "Column", columnMat, out v.ColumnR);

                var ring = new GameObject("Ring");
                ring.transform.SetParent(root.transform, false);
                ring.transform.localPosition = new Vector3(0, 2.5f, 0);
                ring.AddComponent<MeshFilter>().sharedMesh = ringMesh;
                v.RingR = ring.AddComponent<MeshRenderer>();
                v.RingR.sharedMaterial = ringMat;
                v.RingR.shadowCastingMode = ShadowCastingMode.Off;
                v.Ring = ring.transform;
                Views.Add(v);
            }
        }

        static Transform Prim(PrimitiveType type, Transform parent, string name, Material m, out MeshRenderer r)
        {
            var g = GameObject.CreatePrimitive(type);
            g.name = name;
            Destroy(g.GetComponent<Collider>());
            g.transform.SetParent(parent, false);
            r = g.GetComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
            return g.transform;
        }

        public void UpdateAt(float t)
        {
            float pulse = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 4f);
            foreach (var v in Views)
            {
                v.Bikes = data.BikesAt(v.Index, t, out v.EBikes);
                int cap = v.Info.cap;
                var color = Mats.StationColor(v.Bikes, cap);
                bool sel = v == Selected || v == Hovered;

                float h = v.Bikes < 0 ? 4f : Mathf.Clamp(v.Bikes * metersPerBike, 4f, maxHeight);
                float w = columnWidth * (sel ? 1.35f : 1f);
                v.Column.localScale = new Vector3(w, h, w);
                v.Column.localPosition = new Vector3(0, h * 0.5f + 2f, 0);

                mpb.Clear();
                Mats.SetColor(mpb, sel ? Color.Lerp(color, Color.white, 0.35f) : color);
                v.ColumnR.SetPropertyBlock(mpb);
                mpb.Clear();
                Mats.SetColor(mpb, Color.Lerp(color, Color.black, 0.45f));
                v.BaseR.SetPropertyBlock(mpb);

                // pierscien: pulsuje na pustej stacji, staly na przepelnionej, bialy na wybranej
                bool empty = v.Bikes >= 0 && v.Bikes < 0.5f;
                bool over = v.Bikes > cap;
                if (sel || empty || over)
                {
                    v.RingR.enabled = true;
                    float r = columnWidth * (empty ? 2.2f + 1.6f * pulse : 2.4f);
                    v.Ring.localScale = new Vector3(r, 1, r);
                    var rc = sel ? Color.white : empty ? Mats.Empty : Mats.Overfull;
                    rc.a = sel ? 0.9f : empty ? 0.35f + 0.5f * (1 - pulse) : 0.55f;
                    mpb.Clear();
                    mpb.SetColor("_Color", rc);
                    v.RingR.SetPropertyBlock(mpb);
                }
                else v.RingR.enabled = false;
            }
        }

        public StationView ViewOf(Collider c)
        {
            if (c == null) return null;
            foreach (var v in Views) if (v.Root == c.transform) return v;
            return null;
        }

        static Mesh RingMesh(float outer, float inner, int seg)
        {
            var v = new List<Vector3>(); var t = new List<int>(); var c = new List<Color>();
            for (int i = 0; i <= seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(d * outer); v.Add(d * inner); c.Add(Color.white); c.Add(Color.white);
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
