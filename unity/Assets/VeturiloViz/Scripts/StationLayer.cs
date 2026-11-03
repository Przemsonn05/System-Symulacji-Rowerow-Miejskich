// Stacje: slupek 3D, pierscien pustej / przepelnionej / wybranej stacji, poswiata na szczycie.
// Trzy widoki: zapelnienie (stan teraz), bilans ostatniej godziny (skad ubywa rowerow), H2 (gdzie najczesciej brakuje).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public enum ViewMode { Fill, Balance, Problem }

    public class StationView
    {
        public int Index;
        public StationInfo Info;
        public Transform Root, Column, Base, Ring;
        public MeshRenderer ColumnR, BaseR, RingR;
        public float Bikes, EBikes;
        public int Departures, Arrivals;   // ostatnia godzina
        public Color Color;
        public float Height;
    }

    public class StationLayer : MonoBehaviour
    {
        public float metersPerBike = 14f;
        public float columnWidth = 42f;
        public float maxHeight = 700f;
        public float balanceWindowSec = 3600f;

        public readonly List<StationView> Views = new List<StationView>();
        public ViewMode Mode = ViewMode.Fill;
        public StationView Selected { get; set; }
        public StationView Hovered { get; set; }

        DataStore data;
        MaterialPropertyBlock mpb;
        Material ringMat, baseMat, columnMat;
        ParticleSystem glow;
        ParticleSystem.Particle[] glowParticles;
        Camera cam;

        public void Build(DataStore d)
        {
            data = d;
            cam = Camera.main;
            mpb = new MaterialPropertyBlock();
            columnMat = Mats.Unlit(Color.white);
            baseMat = Mats.Unlit(Color.white);
            ringMat = CityBuilder.Queue(Mats.Vertex(Color.white), 3010);
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
                v.Base.localScale = new Vector3(columnWidth * 1.6f, 3f, columnWidth * 1.6f);
                v.Base.localPosition = new Vector3(0, 3f, 0);

                v.Column = Prim(PrimitiveType.Cube, root.transform, "Column", columnMat, out v.ColumnR);

                var ring = new GameObject("Ring");
                ring.transform.SetParent(root.transform, false);
                ring.transform.localPosition = new Vector3(0, 6.5f, 0);
                ring.AddComponent<MeshFilter>().sharedMesh = ringMesh;
                v.RingR = ring.AddComponent<MeshRenderer>();
                v.RingR.sharedMaterial = ringMat;
                v.RingR.shadowCastingMode = ShadowCastingMode.Off;
                v.Ring = ring.transform;
                Views.Add(v);
            }
            Fx.SetLayerRecursive(gameObject, gameObject.layer);
            glow = Fx.GlowSystem(transform, "StationGlow", data.Stations.Length, 3100);
            glowParticles = new ParticleSystem.Particle[data.Stations.Length];
        }

        static Transform Prim(PrimitiveType type, Transform parent, string name, Material m, out MeshRenderer r)
        {
            var g = GameObject.CreatePrimitive(type);
            g.name = name;
            Destroy(g.GetComponent<Collider>());
            g.transform.SetParent(parent, false);
            r = g.GetComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.On;
            r.receiveShadows = false;
            return g.transform;
        }

        public void UpdateAt(float t, float night01)
        {
            float pulse = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 4f);
            float camH = cam ? Mathf.Abs(cam.transform.position.y) + 500f : 5000f;
            float glowSize = Mathf.Clamp(camH * 0.012f, 40f, 260f);
            // z daleka slupki sa szersze - inaczej z widoku calego miasta bylyby ledwo widoczne
            float widthScale = Mathf.Clamp(camH / 5000f, 1f, 2.4f) * (Mode == ViewMode.Problem ? 1.3f : 1f);
            int gi = 0;
            foreach (var v in Views)
            {
                v.Bikes = data.BikesAt(v.Index, t, out v.EBikes);
                data.FlowAt(v.Index, t, balanceWindowSec, out v.Departures, out v.Arrivals);
                int cap = v.Info.cap;
                bool sel = v == Selected || v == Hovered;
                bool empty = v.Bikes >= 0 && v.Bikes < 0.5f;

                float h; Color color;
                switch (Mode)
                {
                    case ViewMode.Balance:
                        int net = v.Arrivals - v.Departures;
                        h = net == 0 ? 6f : Mathf.Clamp(Mathf.Abs(net) * 30f, 10f, maxHeight);
                        color = Mats.BalanceColor(net);
                        break;
                    case ViewMode.Problem:
                        h = Mathf.Clamp(v.Info.shareEmpty * 1500f, 6f, maxHeight * 1.2f);
                        color = Mats.ProblemColor(data.EmptyRank[v.Index], v.Info.shareEmpty);
                        break;
                    default:
                        h = v.Bikes < 0 ? 4f : Mathf.Clamp(v.Bikes * metersPerBike, 4f, maxHeight);
                        color = Mats.StationColor(v.Bikes, cap);
                        break;
                }
                v.Color = color; v.Height = h;

                float w = columnWidth * widthScale * (sel ? 1.35f : 1f);
                v.Column.localScale = new Vector3(w, h, w);
                v.Column.localPosition = new Vector3(0, h * 0.5f + 6f, 0);

                mpb.Clear();
                Mats.SetColor(mpb, sel ? Color.Lerp(color, Color.white, 0.35f) : color);
                v.ColumnR.SetPropertyBlock(mpb);
                mpb.Clear();
                Mats.SetColor(mpb, Color.Lerp(color, Color.black, 0.55f));
                v.BaseR.SetPropertyBlock(mpb);

                // pierscien: pulsuje na pustej stacji (w kazdym widoku - to "problem na zywo"), bialy na wybranej
                if (sel || empty)
                {
                    v.RingR.enabled = true;
                    float r = columnWidth * widthScale * (empty && !sel ? 2.2f + 1.6f * pulse : 2.4f);
                    v.Ring.localScale = new Vector3(r, 1, r);
                    var rc = sel ? Color.white : Mats.Empty;
                    rc.a = sel ? 0.9f : 0.35f + 0.5f * (1 - pulse);
                    mpb.Clear();
                    mpb.SetColor("_Color", rc);
                    v.RingR.SetPropertyBlock(mpb);
                }
                else v.RingR.enabled = false;

                // poswiata na szczycie slupka - mocniejsza noca
                var gc = color; gc.a = Mathf.Lerp(0.28f, 0.75f, night01) * (sel ? 1.4f : 1f);
                glowParticles[gi].position = v.Root.position + Vector3.up * (h + 8f);
                glowParticles[gi].startSize = glowSize * (sel ? 1.6f : 1f);
                glowParticles[gi].startColor = gc;
                glowParticles[gi].remainingLifetime = 1000f;
                glowParticles[gi].startLifetime = 1000f;
                gi++;
            }
            glow.SetParticles(glowParticles, gi);
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
