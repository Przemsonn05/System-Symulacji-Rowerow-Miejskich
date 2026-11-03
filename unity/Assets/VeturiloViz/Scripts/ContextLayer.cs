// Kontekst miasta z danych: wydarzenia (slup swiatla nad obiektem w trakcie wydarzenia),
// korki TomTom na 10 arteriach (znacznik w kolorze spowolnienia) i utrudnienia drogowe (wypadki, zamkniecia, roboty).
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class ContextLayer : MonoBehaviour
    {
        public float labelScale = 0.016f;

        DataStore data;
        Camera cam;
        Material beamMat, discMat, pillarMat;
        Mesh disc;
        MaterialPropertyBlock mpb;

        class EventView { public EventInfo info; public GameObject root; public MeshRenderer beam; public TextMesh label; }
        class CorridorView { public Corridor info; public GameObject root; public MeshRenderer disc, pillar; public TextMesh label; }

        readonly List<EventView> events = new List<EventView>();
        readonly List<CorridorView> corridors = new List<CorridorView>();
        GameObject trafficRoot, eventsRoot;
        ParticleSystem incidents;
        ParticleSystem.Particle[] incBuf = new ParticleSystem.Particle[256];
        int lastStep = -1;

        public bool TrafficOn => trafficRoot != null && trafficRoot.activeSelf;
        public int ActiveIncidents { get; private set; }
        public int ActiveEvents { get; private set; }
        public string ActiveEventNames { get; private set; } = "";

        public void Init(DataStore d)
        {
            data = d;
            cam = Camera.main;
            mpb = new MaterialPropertyBlock();
            beamMat = CityBuilder.Queue(Mats.Glow(), 3050);
            discMat = CityBuilder.Queue(Mats.Vertex(Color.white), 3012);
            pillarMat = Mats.Unlit(Color.white);
            disc = Fx.Disc();
            eventsRoot = new GameObject("Events");
            eventsRoot.transform.SetParent(transform, false);
            trafficRoot = new GameObject("Traffic");
            trafficRoot.transform.SetParent(transform, false);
            incidents = Fx.GlowSystem(trafficRoot.transform, "Incidents", 2000, 3101);
        }

        public void SetTraffic(bool on) { trafficRoot.SetActive(on); }

        public void OnDayLoaded()
        {
            foreach (var e in events) Destroy(e.root);
            events.Clear();
            foreach (var c in corridors) Destroy(c.root);
            corridors.Clear();
            lastStep = -1;

            if (data.Day.eventList != null)
                foreach (var ev in data.Day.eventList) events.Add(CreateEvent(ev));
            if (data.Day.traffic?.corridors != null)
                foreach (var c in data.Day.traffic.corridors) corridors.Add(CreateCorridor(c));
        }

        EventView CreateEvent(EventInfo ev)
        {
            var root = new GameObject("Event");
            root.transform.SetParent(eventsRoot.transform, false);
            root.transform.position = new Vector3(ev.x, 0, ev.z);
            // slup swiatla: wydluzony billboard z miekka tekstura (wyglada jak reflektor w niebo)
            var beam = GameObject.CreatePrimitive(PrimitiveType.Quad);
            Destroy(beam.GetComponent<Collider>());
            beam.name = "Beam";
            beam.transform.SetParent(root.transform, false);
            var r = beam.GetComponent<MeshRenderer>();
            r.sharedMaterial = beamMat;
            r.shadowCastingMode = ShadowCastingMode.Off;
            float h = ev.large == 1 ? 2600f : 1500f;
            beam.transform.localScale = new Vector3(ev.large == 1 ? 420f : 260f, h, 1);
            beam.transform.localPosition = new Vector3(0, h * 0.45f, 0);
            var label = Fx.Label(root.transform, ev.name, Mats.Event, h * 0.92f);
            return new EventView { info = ev, root = root, beam = r, label = label };
        }

        CorridorView CreateCorridor(Corridor c)
        {
            var root = new GameObject("Corridor_" + c.name);
            root.transform.SetParent(trafficRoot.transform, false);
            root.transform.position = new Vector3(c.x, 0, c.z);
            var dg = new GameObject("Disc");
            dg.transform.SetParent(root.transform, false);
            dg.transform.localPosition = new Vector3(0, 6f, 0);
            dg.transform.localScale = new Vector3(110f, 1, 110f);
            dg.AddComponent<MeshFilter>().sharedMesh = disc;
            var dr = dg.AddComponent<MeshRenderer>();
            dr.sharedMaterial = discMat;
            dr.shadowCastingMode = ShadowCastingMode.Off;

            var pillar = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            Destroy(pillar.GetComponent<Collider>());
            pillar.transform.SetParent(root.transform, false);
            var pr = pillar.GetComponent<MeshRenderer>();
            pr.sharedMaterial = pillarMat;
            pr.shadowCastingMode = ShadowCastingMode.Off;
            var label = Fx.Label(root.transform, c.label, Color.white, 0);
            return new CorridorView { info = c, root = root, disc = dr, pillar = pr, label = label };
        }

        public void UpdateAt(float t)
        {
            // wydarzenia: widoczne od 1,5 h przed startem do 30 min po koncu; w trakcie pulsuja
            ActiveEvents = 0;
            var names = new List<string>();
            foreach (var e in events)
            {
                bool on = t >= e.info.start - 5400 && t <= e.info.end + 1800;
                if (e.root.activeSelf != on) e.root.SetActive(on);
                if (!on) continue;
                bool live = t >= e.info.start && t <= e.info.end;
                if (live) { ActiveEvents++; names.Add(e.info.name); }
                float a = live ? 0.55f + 0.2f * Mathf.Sin(Time.unscaledTime * 2.2f) : 0.22f;
                mpb.Clear();
                var c = Mats.Event; c.a = a;
                mpb.SetColor("_TintColor", c * 0.5f);
                mpb.SetColor("_Color", c);
                e.beam.SetPropertyBlock(mpb);
                if (cam)
                {
                    // slup obraca sie tylko wokol pionu (zawsze przodem do kamery)
                    var dir = cam.transform.position - e.beam.transform.position; dir.y = 0;
                    if (dir.sqrMagnitude > 1) e.beam.transform.rotation = Quaternion.LookRotation(-dir);
                    Fx.Face(e.label.transform, cam, labelScale, 30000f);
                    e.label.text = (live ? "● " : "") + e.info.name;
                }
            }
            ActiveEventNames = string.Join(", ", names);

            if (!TrafficOn) return;
            foreach (var c in corridors)
            {
                float cong = data.CongestionAt(c.info, t);
                var col = Mats.CongestionColor(cong);
                const float h = 240f;
                c.pillar.transform.localScale = new Vector3(9f, h * 0.5f, 9f);
                c.pillar.transform.localPosition = new Vector3(0, h * 0.5f, 0);
                mpb.Clear(); Mats.SetColor(mpb, col); c.pillar.SetPropertyBlock(mpb);
                mpb.Clear(); var dc = col; dc.a = 0.45f; mpb.SetColor("_Color", dc); c.disc.SetPropertyBlock(mpb);
                c.label.transform.localPosition = new Vector3(0, h + 20f, 0);
                c.label.text = cong < 0 ? c.info.label : $"{c.info.label} {cong * 100:0}%";
                c.label.color = Color.Lerp(Color.white, col, 0.5f);
                if (cam) Fx.Face(c.label.transform, cam, labelScale * 0.7f, 9000f);
            }

            int step = data.StepAt(t);
            if (step != lastStep)
            {
                lastStep = step;
                var inc = data.Day.incidents;
                var idx = data.IncidentsAt(t);
                ActiveIncidents = idx.Count;
                if (incBuf.Length < idx.Count) incBuf = new ParticleSystem.Particle[idx.Count * 2];
                int g = 0;
                foreach (int i in idx)
                {
                    Color c;
                    switch (inc.cat[i])
                    {
                        case 1: c = new Color(1f, 0.2f, 0.2f, 0.95f); break;          // wypadek
                        case 6: c = new Color(1f, 0.45f, 0.15f, 0.8f); break;         // korek
                        case 9: c = new Color(1f, 0.75f, 0.2f, 0.55f); break;         // roboty
                        default: c = new Color(0.85f, 0.25f, 0.55f, 0.6f); break;     // zamkniety pas / droga
                    }
                    incBuf[g].position = new Vector3(inc.x[i], 12f, inc.z[i]);
                    incBuf[g].startSize = inc.cat[i] == 1 ? 160f : 90f + 25f * Mathf.Clamp(inc.mag[i], 0, 4);
                    incBuf[g].startColor = c;
                    incBuf[g].remainingLifetime = 1000f;
                    incBuf[g].startLifetime = 1000f;
                    g++;
                }
                incidents.SetParticles(incBuf, g);
            }
        }
    }
}
