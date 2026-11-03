// Wspolne efekty: poswiata z czasteczek (ustawianych recznie co klatke, bez emisji) i opisy 3D.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public static class Fx
    {
        /// System czasteczek bez emisji - pozycje, rozmiary i kolory ustawia SetParticles (np. jedna czasteczka na rower).
        public static ParticleSystem GlowSystem(Transform parent, string name, int max, int queue)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.layer = parent.gameObject.layer;
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = true;
            main.playOnAwake = false;
            main.maxParticles = Mathf.Max(max, 1);
            main.startLifetime = 1000f;
            main.startSpeed = 0f;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.useUnscaledTime = true;
            var em = ps.emission; em.enabled = false;
            var shape = ps.shape; shape.enabled = false;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Billboard;
            r.sharedMaterial = CityBuilder.Queue(Mats.Glow(), queue);
            r.shadowCastingMode = ShadowCastingMode.Off;
            r.receiveShadows = false;
            r.maxParticleSize = 0.12f;   // ulamek ekranu - swiatla przy kamerze z bliska nie zaslaniaja widoku
            ps.Play();
            return ps;
        }

        /// Rozblysk: czasteczki emitowane recznie (Emit), gasna i rosna w ciagu ~1 s czasu rzeczywistego.
        public static ParticleSystem FlashSystem(Transform parent, string name, int queue)
        {
            var ps = GlowSystem(parent, name, 2000, queue);
            var main = ps.main;
            main.startLifetime = 1.1f;
            var col = ps.colorOverLifetime;
            col.enabled = true;
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0), new GradientColorKey(Color.white, 1) },
                      new[] { new GradientAlphaKey(1, 0), new GradientAlphaKey(0, 1) });
            col.color = g;
            var size = ps.sizeOverLifetime;
            size.enabled = true;
            size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0, 0.4f, 1, 1.6f));
            return ps;
        }

        public static TextMesh Label(Transform parent, string text, Color c, float y = 0, TextAnchor anchor = TextAnchor.LowerCenter)
        {
            var go = new GameObject("Label");
            go.transform.SetParent(parent, false);
            go.layer = parent.gameObject.layer;
            go.transform.localPosition = new Vector3(0, y, 0);
            var tm = go.AddComponent<TextMesh>();
            tm.font = Ui.DefaultFont;
            tm.fontSize = 64;
            tm.characterSize = 0.1f;
            tm.anchor = anchor;
            tm.alignment = TextAlignment.Center;
            tm.color = c;
            tm.text = text;
            go.GetComponent<MeshRenderer>().sharedMaterial = Ui.DefaultFont.material;
            return tm;
        }

        /// Opis przodem do kamery, staly rozmiar na ekranie; ukryty dalej niz maxDist.
        public static void Face(Transform label, Camera cam, float scale, float maxDist)
        {
            float d = Vector3.Distance(cam.transform.position, label.position);
            bool vis = d < maxDist;
            if (label.gameObject.activeSelf != vis) label.gameObject.SetActive(vis);
            if (!vis) return;
            label.rotation = cam.transform.rotation;
            label.localScale = Vector3.one * (d * scale);
        }

        public static void SetLayerRecursive(GameObject go, int layer)
        {
            go.layer = layer;
            foreach (Transform c in go.transform) SetLayerRecursive(c.gameObject, layer);
        }

        public static Mesh Disc(int seg = 32)
        {
            var v = new List<Vector3> { Vector3.zero }; var t = new List<int>(); var c = new List<Color> { Color.white };
            for (int i = 0; i < seg; i++)
            {
                float a = i * Mathf.PI * 2 / seg;
                v.Add(new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a))); c.Add(Color.white);
                t.Add(0); t.Add(1 + (i + 1) % seg); t.Add(1 + i);
            }
            var m = new Mesh();
            m.SetVertices(v); m.SetColors(c); m.SetTriangles(t, 0); m.RecalculateBounds();
            return m;
        }
    }
}
