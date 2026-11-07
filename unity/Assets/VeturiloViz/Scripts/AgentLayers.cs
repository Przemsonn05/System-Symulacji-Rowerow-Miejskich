// Warstwy "jak agenci wplywaja na siebie":
//   AgentLayer    - klienci z symulacji: czekaja przy pustej stacji, ida do sasiedniej, rezygnuja (ikona ✕);
//                   decyzje dyspozytora (linia od stacji, ktora potrzebuje rowerow, do ciezarowki z zadaniem);
//                   sygnaly stacji. Kolor klienta = typ (dojezdzajacy, student, rekreacyjny, e-rowerzysta).
//   CascadeLayer  - fale pustek (src.metrics): stacja pustoszeje, chwile pozniej sasiednia - linie miedzy nimi.
//   PressureLayer - "cisnienie" stacji jako mapa ciepla na ziemi: czerwony = brakuje rowerow (mniej niz zwykle,
//                   pusta), niebieski = za duzo (wiecej niz zwykle) - widac "oddychanie miasta" rano i po poludniu.
// Wszystkie dzialaja dla danych i symulacji (agenci tylko w symulacji - w danych nie znamy pojedynczych klientow).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class AgentLayer : MonoBehaviour
    {
        public bool showPeople = true;
        public bool showDispatch = true;
        public const float WaitBefore = 240f;   // klient stoi przy pustej stacji przed decyzja [s czasu symulacji]
        public const float LeaveAfter = 360f;   // odchodzi z ikona ✕
        public const float WalkPre = 120f;
        const float StandRadius = 70f;                 // promien, na ktorym stoja klienci wokol stacji [m]

        class Person { public GameObject go; public MeshRenderer r; }
        class Cross { public Transform holder; public TextMesh tm; }

        DataStore data;
        Camera cam;
        Mesh personMesh;
        Material personMat, lineMat;
        MaterialPropertyBlock mpb;
        readonly List<Person> people = new List<Person>();
        readonly List<Cross> crosses = new List<Cross>();
        readonly List<LineRenderer> lines = new List<LineRenderer>();
        readonly List<Cross> taskLabels = new List<Cross>();
        readonly Dictionary<int, List<int>> legsByTruck = new Dictionary<int, List<int>>();
        ParticleSystem glow;
        ParticleSystem.Particle[] glowBuf = new ParticleSystem.Particle[256];
        int nPeople, nCross, nLines, nTaskLabels, nGlow;
        bool[] signal;

        public int Waiting { get; private set; }
        public int Walking { get; private set; }
        public int Leaving { get; private set; }
        public int ActiveTasks { get; private set; }
        public int Signals { get; private set; }
        public bool HasAgents => data?.Day?.agents?.lostT != null && data.IsSim;

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            mpb = new MaterialPropertyBlock();
            personMat = Mats.Unlit(Color.white);
            lineMat = CityBuilder.Queue(Mats.Vertex(Color.white), 3030);
            personMesh = PersonMesh();
            glow = Fx.GlowSystem(transform, "AgentGlow", 2000, 3103);
        }

        public void OnDayLoaded()
        {
            legsByTruck.Clear();
            var tk = data.Day.trucks;
            if (tk?.truck != null)
                for (int i = 0; i < tk.dep.Length && i < tk.truck.Length; i++)
                {
                    if (!legsByTruck.TryGetValue(tk.truck[i], out var l)) legsByTruck[tk.truck[i]] = l = new List<int>();
                    l.Add(i);
                }
            signal = new bool[data.Stations.Length];
        }

        public int DrawnLines => nLines;
        public int DrawnGlows => nGlow;

        readonly List<MeshRenderer> rings = new List<MeshRenderer>();
        int nRings;
        Mesh ringMesh;

        void Ring(Vector3 pos, float radius, Color c)
        {
            if (ringMesh == null) ringMesh = RingMesh();
            if (nRings == rings.Count)
            {
                var go = new GameObject("AgentRing");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = ringMesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = lineMat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                rings.Add(r);
            }
            var ring = rings[nRings++];
            if (!ring.enabled) ring.enabled = true;
            ring.transform.position = new Vector3(pos.x, 9f, pos.z);
            ring.transform.localScale = new Vector3(radius, 1, radius);
            mpb.Clear();
            mpb.SetColor("_Color", c);
            ring.SetPropertyBlock(mpb);
        }

        public static Mesh RingMesh()
        {
            var v = new List<Vector3>(); var t = new List<int>(); var c = new List<Color>();
            const int seg = 48;
            for (int i = 0; i <= seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(d); v.Add(d * 0.78f); c.Add(Color.white); c.Add(Color.white);
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

        public void UpdateAt(float t, float night01)
        {
            nPeople = nCross = nLines = nTaskLabels = nGlow = nRings = 0;
            Waiting = Walking = Leaving = ActiveTasks = Signals = 0;
            var ag = data.Day?.agents;
            if (ag != null && data.IsSim)
            {
                float camH = cam ? Mathf.Abs(cam.transform.position.y) : 3000f;
                // ludziki stoja wokol stacji (poza slupkiem ~40 m) i rosna z odlegloscia kamery
                float size = Mathf.Clamp(camH * 0.008f, 9f, 60f);
                if (showPeople) { People(ag, t, size); }
                if (showDispatch) { Dispatch(ag, t, size, camH); Signal(ag, t, size); }
            }
            for (int i = nPeople; i < people.Count; i++) if (people[i].go.activeSelf) people[i].go.SetActive(false);
            for (int i = nCross; i < crosses.Count; i++) if (crosses[i].holder.gameObject.activeSelf) crosses[i].holder.gameObject.SetActive(false);
            for (int i = nLines; i < lines.Count; i++) if (lines[i].enabled) lines[i].enabled = false;
            for (int i = nTaskLabels; i < taskLabels.Count; i++) if (taskLabels[i].holder.gameObject.activeSelf) taskLabels[i].holder.gameObject.SetActive(false);
            for (int i = nRings; i < rings.Count; i++) if (rings[i].enabled) rings[i].enabled = false;
            glow.SetParticles(glowBuf, nGlow);
        }

        // ------------------------------------------------------------- klienci

        void People(Agents ag, float t, float size)
        {
            var st = data.Stations;
            // rezygnacje: stoi przy pustej stacji, potem odchodzi z ✕
            if (ag.lostT != null)
            {
                int i0 = DataStore.UpperBound(ag.lostT, t - LeaveAfter);
                for (int i = i0; i < ag.lostT.Length && ag.lostT[i] <= t + WaitBefore; i++)
                {
                    var s = st[ag.lostSt[i]];
                    float a = i * 2.39996f;
                    var dir = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                    var basePos = new Vector3(s.x, 0, s.z) + dir * (StandRadius + size * (1.2f + 0.8f * (i % 3)));
                    var c = Mats.UserType(Get(ag.lostType, i));
                    if (t < ag.lostT[i])
                    {
                        Waiting++;
                        float bob = Mathf.Abs(Mathf.Sin(Time.unscaledTime * 3f + i)) * size * 0.25f;
                        Show(basePos + Vector3.up * bob, size, c, 1f);
                    }
                    else
                    {
                        Leaving++;
                        float f = (t - ag.lostT[i]) / LeaveAfter;
                        var p = basePos + dir * size * 14f * f;
                        Show(p, size, Color.Lerp(c, Mats.Leaving, 0.6f), 1f - f * 0.7f);
                        ShowCross(p + Vector3.up * size * (3.4f + 5f * f), 1f - f, size);
                    }
                }
            }
            // przejscie do sasiedniej stacji (z linia trasy)
            if (ag.walkT != null)
                for (int i = 0; i < ag.walkT.Length; i++)
                {
                    float t0 = ag.walkT[i], t1 = Mathf.Max(ag.walkEnd[i], t0 + 30);
                    if (t < t0 - WalkPre || t > t1) continue;
                    var A = st[ag.walkFrom[i]]; var B = st[ag.walkTo[i]];
                    var pa = new Vector3(A.x, 0, A.z); var pb = new Vector3(B.x, 0, B.z);
                    var c = Mats.UserType(Get(ag.walkType, i));
                    var off = (pb - pa).normalized * (StandRadius + size);
                    if (t < t0) { Waiting++; Show(pa + off, size, c, 1f); continue; }
                    Walking++;
                    float f = Mathf.SmoothStep(0, 1, (t - t0) / (t1 - t0));
                    Show(Vector3.Lerp(pa + off, pb - off, f), size, c, 1f);
                    var lr = Line();
                    lr.positionCount = 2;
                    lr.SetPosition(0, pa + Vector3.up * 6f);
                    lr.SetPosition(1, pb + Vector3.up * 6f);
                    lr.widthMultiplier = size * 0.6f;
                    var wc = Mats.Walking; wc.a = 0.75f;
                    lr.startColor = wc; wc.a = 0.25f; lr.endColor = wc;
                }
            // czekanie (nowe zdarzenia agentow, jesli sa)
            if (ag.waitT != null)
                for (int i = 0; i < ag.waitT.Length; i++)
                {
                    if (t < ag.waitT[i] || t > ag.waitEnd[i]) continue;
                    Waiting++;
                    var s = st[ag.waitSt[i]];
                    float a = i * 2.39996f;
                    Show(new Vector3(s.x, 0, s.z) + new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a)) * (StandRadius + size * 1.5f), size,
                         Mats.UserType(Get(ag.waitType, i)), 1f);
                }
        }

        static int Get(int[] a, int i) => a != null && i < a.Length ? a[i] : 0;

        void Show(Vector3 pos, float size, Color c, float scale)
        {
            if (nPeople == people.Count) people.Add(NewPerson());
            var p = people[nPeople++];
            if (!p.go.activeSelf) p.go.SetActive(true);
            p.go.transform.position = new Vector3(pos.x, pos.y, pos.z);
            p.go.transform.localScale = Vector3.one * size * Mathf.Max(scale, 0.05f);
            mpb.Clear();
            Mats.SetColor(mpb, c);
            p.r.SetPropertyBlock(mpb);
            AddGlow(pos + Vector3.up * size * 1.6f, size * 4.5f, new Color(c.r, c.g, c.b, 0.45f * scale));
        }

        void AddGlow(Vector3 pos, float size, Color c)
        {
            if (nGlow >= glowBuf.Length) System.Array.Resize(ref glowBuf, glowBuf.Length * 2);
            glowBuf[nGlow].position = pos;
            glowBuf[nGlow].startSize = size;
            glowBuf[nGlow].startColor = c;
            glowBuf[nGlow].remainingLifetime = 1000f;
            glowBuf[nGlow].startLifetime = 1000f;
            nGlow++;
        }

        void ShowCross(Vector3 pos, float alpha, float size)
        {
            if (nCross == crosses.Count) crosses.Add(NewLabel("✕", Mats.Leaving, crosses.Count));
            var c = crosses[nCross++];
            if (!c.holder.gameObject.activeSelf) c.holder.gameObject.SetActive(true);
            c.holder.position = pos;
            var col = Mats.Leaving; col.a = Mathf.Clamp01(alpha);
            c.tm.color = col;
            Face(c.tm.transform, 0.028f);
        }

        Person NewPerson()
        {
            var go = new GameObject("Agent");
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = personMesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = personMat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            return new Person { go = go, r = r };
        }

        Cross NewLabel(string text, Color c, int k)
        {
            var holder = new GameObject("AgentLabel" + k);
            holder.layer = gameObject.layer;
            holder.transform.SetParent(transform, false);
            var tm = Fx.Label(holder.transform, text, c);
            tm.fontStyle = FontStyle.Bold;
            return new Cross { holder = holder.transform, tm = tm };
        }

        LineRenderer Line()
        {
            if (nLines == lines.Count)
            {
                var go = new GameObject("AgentLine");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                var lr = go.AddComponent<LineRenderer>();
                lr.sharedMaterial = lineMat;
                lr.useWorldSpace = true;
                lr.shadowCastingMode = ShadowCastingMode.Off;
                lr.receiveShadows = false;
                lr.numCapVertices = 2;
                lr.alignment = LineAlignment.View;
                lines.Add(lr);
            }
            var l = lines[nLines++];
            l.enabled = true;
            return l;
        }

        void Face(Transform label, float scale)
        {
            if (cam == null) return;
            label.rotation = cam.transform.rotation;
            label.localScale = Vector3.one * Vector3.Distance(cam.transform.position, label.position) * scale;
        }

        // ------------------------------------------------------------- dyspozytor

        void Dispatch(Agents ag, float t, float size, float camH)
        {
            if (ag.taskT0 == null) return;
            var st = data.Stations;
            for (int i = 0; i < ag.taskT0.Length; i++)
            {
                if (t < ag.taskT0[i] || t > ag.taskT1[i]) continue;
                ActiveTasks++;
                var drop = st[ag.taskDrop[i]]; var pick = st[ag.taskPick[i]];
                var target = new Vector3(drop.x, 0, drop.z);
                var truck = TruckPos(ag.taskTruck[i], t, new Vector3(pick.x, 0, pick.z), target);
                // luk: ciezarowka -> stacja, ktora potrzebuje rowerow
                var lr = Line();
                const int n = 24;
                lr.positionCount = n;
                float d = Vector3.Distance(truck, target);
                float h = Mathf.Clamp(d * 0.22f, 60f, 900f);
                for (int k = 0; k < n; k++)
                {
                    float f = k / (n - 1f);
                    var p = Vector3.Lerp(truck, target, f);
                    p.y = 30f + Mathf.Sin(f * Mathf.PI) * h;
                    lr.SetPosition(k, p);
                }
                lr.widthMultiplier = Mathf.Clamp(camH * 0.007f, 10f, 110f);
                float blink = 0.7f + 0.3f * Mathf.Sin(Time.unscaledTime * 4f + i);
                var c = Mats.Dispatch; c.a = blink;
                lr.startColor = c; c.a = 0.55f; lr.endColor = c;
                Ring(target, Mathf.Clamp(camH * 0.03f, 90f, 500f), new Color(c.r, c.g, c.b, 0.55f * blink));
                AddGlow(target + Vector3.up * 40f, Mathf.Clamp(camH * 0.08f, 150f, 1200f), new Color(c.r, c.g, c.b, 0.7f * blink));
                AddGlow(truck + Vector3.up * 40f, Mathf.Clamp(camH * 0.05f, 100f, 800f), new Color(c.r, c.g, c.b, 0.6f * blink));
                if (nTaskLabels == taskLabels.Count) taskLabels.Add(NewLabel("", Mats.Dispatch, taskLabels.Count));
                var lab = taskLabels[nTaskLabels++];
                if (!lab.holder.gameObject.activeSelf) lab.holder.gameObject.SetActive(true);
                lab.holder.position = target + Vector3.up * (h * 0.15f + 120f);
                lab.tm.text = $"ciężarówka {ag.taskTruck[i] + 1}" + (ag.taskN[i] > 0 ? $" · +{ag.taskN[i]}" : "");
                Face(lab.tm.transform, 0.016f);
            }
        }

        /// Polozenie ciezarowki o numerze id w chwili t (odcinek jazdy w toku albo ostatnia stacja).
        Vector3 TruckPos(int id, float t, Vector3 pick, Vector3 drop)
        {
            var tk = data.Day.trucks;
            if (!legsByTruck.TryGetValue(id, out var legs)) return pick;
            int last = -1;
            foreach (int i in legs)
            {
                if (tk.dep[i] > t) break;
                last = i;
                if (tk.arr[i] > t)
                {
                    int r = tk.route[i];
                    if (r < 0 || r >= data.TruckRoutes.Length) break;
                    float f = Mathf.SmoothStep(0, 1, (t - tk.dep[i]) / Mathf.Max(tk.arr[i] - tk.dep[i], 1));
                    var p = data.TruckRoutes[r].Sample(f, out _);
                    return new Vector3(p.x, 0, p.y);
                }
            }
            if (last >= 0)
            {
                var s = data.Stations[tk.toSt[last]];
                return new Vector3(s.x, 0, s.z);
            }
            return pick;
        }

        void Signal(Agents ag, float t, float size)
        {
            if (ag.sigT == null || ag.sigT.Length == 0) return;
            System.Array.Clear(signal, 0, signal.Length);
            for (int i = 0; i < ag.sigT.Length && ag.sigT[i] <= t; i++) signal[ag.sigSt[i]] = ag.sigOn[i] == 1;
            float blink = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 6f);
            for (int s = 0; s < signal.Length; s++)
            {
                if (!signal[s]) continue;
                Signals++;
                var st = data.Stations[s];
                AddGlow(new Vector3(st.x, size * 14f, st.z), size * 10f, new Color(1f, 0.2f, 0.25f, 0.4f + 0.5f * blink));
            }
        }

        /// Ludzik: walec (tulow) + kula (glowa), wysokosc ok. 3 jednostek, podstawa na y = 0.
        static Mesh PersonMesh()
        {
            var v = new List<Vector3>(); var t = new List<int>(); var n = new List<Vector3>();
            const int seg = 10;
            // tulow - stozek scietny
            for (int i = 0; i <= seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v.Add(d * 0.55f); n.Add(d);
                v.Add(d * 0.42f + Vector3.up * 1.9f); n.Add(d);
                if (i < seg) { int b = i * 2; t.Add(b); t.Add(b + 1); t.Add(b + 2); t.Add(b + 1); t.Add(b + 3); t.Add(b + 2); }
            }
            // glowa - kula
            int start = v.Count;
            const int rings = 6;
            var c = new Vector3(0, 2.45f, 0);
            for (int r = 0; r <= rings; r++)
            {
                float phi = Mathf.PI * r / rings;
                for (int i = 0; i <= seg; i++)
                {
                    float a = i * Mathf.PI * 2 / seg;
                    var d = new Vector3(Mathf.Sin(phi) * Mathf.Cos(a), Mathf.Cos(phi), Mathf.Sin(phi) * Mathf.Sin(a));
                    v.Add(c + d * 0.42f); n.Add(d);
                }
            }
            for (int r = 0; r < rings; r++)
                for (int i = 0; i < seg; i++)
                {
                    int a0 = start + r * (seg + 1) + i, a1 = a0 + seg + 1;
                    t.Add(a0); t.Add(a0 + 1); t.Add(a1); t.Add(a0 + 1); t.Add(a1 + 1); t.Add(a1);
                }
            var m = new Mesh();
            m.SetVertices(v); m.SetNormals(n); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }

    // =================================================================================== fale pustek

    public class CascadeLayer : MonoBehaviour
    {
        public const float Fade = 1800f;       // fala znika 30 min po ostatniej stacji
        public const float LinkM = 800f;

        DataStore data;
        Camera cam;
        Material lineMat;
        readonly List<LineRenderer> lines = new List<LineRenderer>();
        readonly List<TextMesh> labels = new List<TextMesh>();
        readonly List<MeshRenderer> rings = new List<MeshRenderer>();
        ParticleSystem glow;
        ParticleSystem.Particle[] buf = new ParticleSystem.Particle[256];
        int nLines, nLabels, nGlow, nRings;
        Mesh ringMesh;
        MaterialPropertyBlock mpb;

        public int DrawnLines => nLines;
        public int DrawnRings => nRings;

        public int Active { get; private set; }
        public int ActiveStations { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            lineMat = CityBuilder.Queue(Mats.Vertex(Color.white), 3028);
            glow = Fx.GlowSystem(transform, "CascadeGlow", 1000, 3104);
            ringMesh = AgentLayer.RingMesh();
            mpb = new MaterialPropertyBlock();
        }

        public void UpdateAt(float t)
        {
            nLines = nLabels = nGlow = nRings = 0;
            Active = ActiveStations = 0;
            var c = data.Day?.cascades;
            float camH = cam ? Mathf.Abs(cam.transform.position.y) : 3000f;
            if (c?.start != null)
                for (int k = 0; k < c.start.Length; k++)
                {
                    int a = c.start[k], n = c.len[k];
                    float t0 = c.t[a], t1 = c.t[a + n - 1];
                    if (t < t0 || t > t1 + Fade) continue;
                    Active++;
                    float alpha = t > t1 ? 1f - (t - t1) / Fade : 1f;
                    int shown = 0;
                    for (int i = 0; i < n; i++)
                    {
                        if (c.t[a + i] > t) break;
                        shown++;
                        var s = data.Stations[c.st[a + i]];
                        var p = new Vector3(s.x, 0, s.z);
                        float age = t - c.t[a + i];
                        float fresh = Mathf.Clamp01(1f - age / 600f);
                        float pulse = 0.75f + 0.25f * Mathf.Sin(Time.unscaledTime * 5f + i);
                        AddGlow(p + Vector3.up * 25f, Mathf.Clamp(camH * 0.07f, 140f, 1100f) * (1f + fresh * 0.8f),
                                new Color(Mats.Cascade.r, Mats.Cascade.g, Mats.Cascade.b, (0.45f + 0.45f * fresh) * alpha * pulse));
                        Ring(p, Mathf.Clamp(camH * 0.022f, 70f, 380f) * (1f + fresh * 0.6f),
                             new Color(Mats.Cascade.r, Mats.Cascade.g, Mats.Cascade.b, (0.5f + 0.4f * fresh) * alpha));
                        // polaczenie z najblizsza wczesniejsza stacja tej fali (kto "zarazil")
                        int parent = -1; float best = LinkM;
                        for (int j = 0; j < i; j++)
                        {
                            var q = data.Stations[c.st[a + j]];
                            float d = Vector2.Distance(new Vector2(q.x, q.z), new Vector2(s.x, s.z));
                            if (d <= best) { best = d; parent = j; }
                        }
                        if (parent < 0) continue;
                        var ps = data.Stations[c.st[a + parent]];
                        Arc(new Vector3(ps.x, 0, ps.z), p, camH, alpha * (0.55f + 0.45f * fresh));
                    }
                    ActiveStations += shown;
                    var first = data.Stations[c.st[a]];
                    Label(new Vector3(first.x, Mathf.Clamp(camH * 0.03f, 80f, 500f), first.z),
                          $"fala pustek · {shown}/{n}", alpha);
                }
            for (int i = nLines; i < lines.Count; i++) if (lines[i].enabled) lines[i].enabled = false;
            for (int i = nLabels; i < labels.Count; i++) if (labels[i].transform.parent.gameObject.activeSelf) labels[i].transform.parent.gameObject.SetActive(false);
            for (int i = nRings; i < rings.Count; i++) if (rings[i].enabled) rings[i].enabled = false;
            glow.SetParticles(buf, nGlow);
        }

        void AddGlow(Vector3 pos, float size, Color col)
        {
            if (nGlow >= buf.Length) System.Array.Resize(ref buf, buf.Length * 2);
            buf[nGlow].position = pos; buf[nGlow].startSize = size; buf[nGlow].startColor = col;
            buf[nGlow].remainingLifetime = 1000f; buf[nGlow].startLifetime = 1000f;
            nGlow++;
        }

        void Ring(Vector3 pos, float radius, Color c)
        {
            if (nRings == rings.Count)
            {
                var go = new GameObject("CascadeRing");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                go.AddComponent<MeshFilter>().sharedMesh = ringMesh;
                var r = go.AddComponent<MeshRenderer>();
                r.sharedMaterial = lineMat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                rings.Add(r);
            }
            var ring = rings[nRings++];
            if (!ring.enabled) ring.enabled = true;
            ring.transform.position = new Vector3(pos.x, 8f, pos.z);
            ring.transform.localScale = new Vector3(radius, 1, radius);
            mpb.Clear();
            mpb.SetColor("_Color", c);
            ring.SetPropertyBlock(mpb);
        }

        void Arc(Vector3 a, Vector3 b, float camH, float alpha)
        {
            if (nLines == lines.Count)
            {
                var go = new GameObject("CascadeLink");
                go.layer = gameObject.layer;
                go.transform.SetParent(transform, false);
                var lr = go.AddComponent<LineRenderer>();
                lr.sharedMaterial = lineMat;
                lr.useWorldSpace = true;
                lr.shadowCastingMode = ShadowCastingMode.Off;
                lr.alignment = LineAlignment.View;
                lr.positionCount = 12;
                lines.Add(lr);
            }
            var l = lines[nLines++];
            l.enabled = true;
            float h = Mathf.Clamp(Vector3.Distance(a, b) * 0.35f, 40f, 300f);
            for (int k = 0; k < 12; k++)
            {
                float f = k / 11f;
                var p = Vector3.Lerp(a, b, f);
                p.y = 20f + Mathf.Sin(f * Mathf.PI) * h;
                l.SetPosition(k, p);
            }
            l.widthMultiplier = Mathf.Clamp(camH * 0.007f, 10f, 110f);
            var c = Mats.Cascade; c.a = alpha;
            l.startColor = c; c.a = alpha * 0.6f; l.endColor = c;
        }

        void Label(Vector3 pos, string text, float alpha)
        {
            if (nLabels == labels.Count)
            {
                var holder = new GameObject("CascadeLabel");
                holder.layer = gameObject.layer;
                holder.transform.SetParent(transform, false);
                labels.Add(Fx.Label(holder.transform, "", Mats.Cascade));
            }
            var tm = labels[nLabels++];
            var h = tm.transform.parent;
            if (!h.gameObject.activeSelf) h.gameObject.SetActive(true);
            h.position = pos;
            tm.text = text;
            var c = Color.Lerp(Color.white, Mats.Cascade, 0.5f); c.a = alpha;
            tm.color = c;
            if (cam != null)
            {
                tm.transform.rotation = cam.transform.rotation;
                tm.transform.localScale = Vector3.one * Vector3.Distance(cam.transform.position, pos) * 0.016f;
            }
        }
    }

    // =================================================================================== cisnienie

    public class PressureLayer : MonoBehaviour
    {
        public int resolution = 256;
        public float sigma = 330f;   // promien rozmycia wplywu stacji [m]

        DataStore data;
        Texture2D tex;
        Color32[] px;
        float[] sum, wsum;
        float x0, z0, cell;
        int w, h;
        float lastT = -1, nextUpdate;

        public float ShortageShare { get; private set; }

        public void Init(DataStore d)
        {
            data = d;
            float minX = float.MaxValue, maxX = float.MinValue, minZ = float.MaxValue, maxZ = float.MinValue;
            foreach (var s in d.Stations)
            {
                minX = Mathf.Min(minX, s.x); maxX = Mathf.Max(maxX, s.x);
                minZ = Mathf.Min(minZ, s.z); maxZ = Mathf.Max(maxZ, s.z);
            }
            float pad = sigma * 4f;
            x0 = minX - pad; z0 = minZ - pad;
            float sx = maxX - minX + 2 * pad, sz = maxZ - minZ + 2 * pad;
            cell = Mathf.Max(sx, sz) / resolution;
            w = Mathf.CeilToInt(sx / cell); h = Mathf.CeilToInt(sz / cell);
            tex = new Texture2D(w, h, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Bilinear, name = "Pressure" };
            px = new Color32[w * h];
            sum = new float[w * h]; wsum = new float[w * h];

            var go = new GameObject("PressureMap");
            go.layer = gameObject.layer;
            go.transform.SetParent(transform, false);
            var mesh = new Mesh();
            float y = 4f;
            mesh.vertices = new[] { new Vector3(x0, y, z0), new Vector3(x0 + w * cell, y, z0), new Vector3(x0, y, z0 + h * cell), new Vector3(x0 + w * cell, y, z0 + h * cell) };
            mesh.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1) };
            mesh.colors = new[] { Color.white, Color.white, Color.white, Color.white };
            mesh.triangles = new[] { 0, 2, 1, 1, 2, 3 };
            mesh.RecalculateBounds();
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            var m = CityBuilder.Queue(Mats.Vertex(Color.white), 2995);
            m.mainTexture = tex;
            r.sharedMaterial = m;
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
        }

        public void OnDayLoaded() => lastT = -1;

        public void UpdateAt(float t)
        {
            if (!gameObject.activeSelf) return;
            if (lastT >= 0 && (Mathf.Abs(t - lastT) < 45f || Time.unscaledTime < nextUpdate)) return;
            lastT = t;
            nextUpdate = Time.unscaledTime + 0.2f;
            System.Array.Clear(sum, 0, sum.Length);
            System.Array.Clear(wsum, 0, wsum.Length);
            int rad = Mathf.CeilToInt(sigma * 3f / cell);
            float inv = 1f / (2f * sigma * sigma);
            int shortage = 0, known = 0;
            for (int i = 0; i < data.Stations.Length; i++)
            {
                float p = data.PressureAt(i, t);
                if (float.IsNaN(p)) continue;
                known++;
                if (p < -0.5f) shortage++;
                var s = data.Stations[i];
                int cx = Mathf.FloorToInt((s.x - x0) / cell), cz = Mathf.FloorToInt((s.z - z0) / cell);
                for (int dz = -rad; dz <= rad; dz++)
                {
                    int z = cz + dz;
                    if (z < 0 || z >= h) continue;
                    for (int dx = -rad; dx <= rad; dx++)
                    {
                        int x = cx + dx;
                        if (x < 0 || x >= w) continue;
                        float ddx = (x + 0.5f) * cell + x0 - s.x, ddz = (z + 0.5f) * cell + z0 - s.z;
                        float wt = Mathf.Exp(-(ddx * ddx + ddz * ddz) * inv);
                        int k = z * w + x;
                        sum[k] += wt * p; wsum[k] += wt;
                    }
                }
            }
            ShortageShare = known > 0 ? shortage / (float)known : 0;
            for (int k = 0; k < px.Length; k++)
            {
                float ws = wsum[k];
                if (ws < 1e-4f) { px[k] = new Color32(0, 0, 0, 0); continue; }
                float v = sum[k] / ws;
                float cover = 1f - Mathf.Exp(-ws / 0.6f);
                var c = v < 0 ? Mats.Shortage : Mats.Surplus;
                float a = Mathf.Clamp01(Mathf.Abs(v) * 1.25f) * cover * 0.78f;
                px[k] = new Color32((byte)(c.r * 255), (byte)(c.g * 255), (byte)(c.b * 255), (byte)(a * 255));
            }
            tex.SetPixels32(px);
            tex.Apply(false);
        }
    }
}
