// Pora dnia i pogoda z danych: pozycja slonca (wysokosc z Open-Meteo / astral), zachmurzenie, mgla, deszcz.
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class EnvironmentFx : MonoBehaviour
    {
        public Light sun;
        public float rainPerMm = 9000f;
        ParticleSystem rain;
        Camera cam;
        Material sky;

        public float SunElevation { get; private set; }
        public float Precip { get; private set; }
        public float Cloud { get; private set; }
        public bool IsNight => SunElevation < -4f;

        public void Init(Camera c)
        {
            cam = c;
            sun = FindSun();
            sun.type = LightType.Directional;
            sun.shadows = LightShadows.Soft;
            RenderSettings.sun = sun;
            if (RenderSettings.skybox != null)
            {
                sky = new Material(RenderSettings.skybox);
                RenderSettings.skybox = sky;
            }
            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Exponential;
            rain = CreateRain();
        }

        static Light FindSun()
        {
            foreach (var l in Object.FindObjectsByType<Light>(FindObjectsSortMode.None))
                if (l.type == LightType.Directional) return l;
            var go = new GameObject("Sun");
            return go.AddComponent<Light>();
        }

        public void UpdateAt(DataStore data, float t)
        {
            var h = data.Day.hours;
            SunElevation = data.HourValue(h.sunElevation, t);
            Precip = data.HourValue(h.precip, t);
            Cloud = data.HourValue(h.cloud, t) / 100f;

            // azymut: z grubsza 15 stopni na godzine, poludnie o 12:00 czasu slonecznego (~11:35 w Warszawie zima)
            float solarHour = t / 3600f - 0.4f;
            float azimuth = (solarHour - 12f) * 15f + 180f;
            float elev = SunElevation;
            // ponizej horyzontu: swiatlo ksiezyca z gory, zeby miasto nie bylo calkiem czarne
            bool night = elev < -4f;
            float lightElev = night ? 35f : Mathf.Max(elev, 2f);
            sun.transform.rotation = Quaternion.Euler(lightElev, azimuth, 0);

            float day = Mathf.Clamp01((elev + 6f) / 18f);          // 0 noc .. 1 dzien
            float cloudDim = Mathf.Lerp(1f, 0.55f, Cloud);
            sun.intensity = night ? 0.12f : Mathf.Lerp(0.25f, 1.25f, day) * cloudDim;
            var warm = new Color(1f, 0.72f, 0.48f);
            sun.color = night ? new Color(0.55f, 0.65f, 1f) : Color.Lerp(warm, Color.white, Mathf.Clamp01(elev / 20f));

            var ambDay = new Color(0.55f, 0.58f, 0.64f);
            var ambNight = new Color(0.07f, 0.08f, 0.13f);
            RenderSettings.ambientLight = Color.Lerp(ambNight, ambDay, day) * Mathf.Lerp(1f, 0.85f, Cloud);

            var fogDay = Color.Lerp(new Color(0.62f, 0.70f, 0.80f), new Color(0.55f, 0.57f, 0.60f), Cloud);
            var fogNight = new Color(0.03f, 0.04f, 0.07f);
            RenderSettings.fogColor = Color.Lerp(fogNight, fogDay, day);
            RenderSettings.fogDensity = Mathf.Lerp(0.000035f, 0.00009f, Mathf.Max(Cloud * 0.6f, Mathf.Clamp01(Precip / 2f)));
            if (cam)
            {
                cam.clearFlags = sky != null ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
                cam.backgroundColor = RenderSettings.fogColor;
            }
            if (sky != null && sky.HasProperty("_Exposure")) sky.SetFloat("_Exposure", Mathf.Lerp(0.15f, 1.2f, day) * cloudDim);

            // deszcz: emisja proporcjonalna do opadu, system podaza za kamera
            var em = rain.emission;
            em.rateOverTime = Precip > 0.05f ? Mathf.Clamp(Precip * rainPerMm, 1500f, 20000f) : 0f;
            if (cam)
            {
                var p = cam.transform.position;
                rain.transform.position = new Vector3(p.x, Mathf.Max(p.y * 0.6f, 400f), p.z) + cam.transform.forward * 600f;
            }
        }

        ParticleSystem CreateRain()
        {
            var go = new GameObject("Rain");
            go.transform.SetParent(transform, false);
            var ps = go.AddComponent<ParticleSystem>();
            ps.Stop(true, ParticleSystemStopBehavior.StopEmittingAndClear);
            var main = ps.main;
            main.loop = true;
            main.startLifetime = 1.2f;
            main.startSpeed = 900f;
            main.startSize = 3f;
            main.maxParticles = 30000;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.startColor = new Color(0.75f, 0.82f, 1f, 0.35f);
            main.useUnscaledTime = true;
            var shape = ps.shape;
            shape.shapeType = ParticleSystemShapeType.Box;
            // pudelko plaskie w lokalnym z; po obrocie o 90 st. wokol x lezy poziomo i emituje w dol
            shape.scale = new Vector3(5000f, 5000f, 10f);
            shape.rotation = new Vector3(90f, 0, 0);
            var em = ps.emission;
            em.rateOverTime = 0;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch;
            r.velocityScale = 0.12f;
            r.lengthScale = 1f;
            r.sharedMaterial = Mats.Vertex(Color.white);
            r.shadowCastingMode = ShadowCastingMode.Off;
            ps.Play();
            return ps;
        }
    }
}
