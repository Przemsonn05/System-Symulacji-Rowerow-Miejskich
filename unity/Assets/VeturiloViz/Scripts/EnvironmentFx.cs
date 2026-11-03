// Pora dnia i pogoda z danych: pozycja slonca (wysokosc z astral / Open-Meteo), niebo, gwiazdy noca,
// zachmurzenie, mgla, deszcz z wiatrem. Night01 steruje swiatlami miasta (okna, latarnie).
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public class EnvironmentFx : MonoBehaviour
    {
        public Light sun;
        public float rainPerMm = 9000f;
        ParticleSystem rain, stars;
        Camera cam;
        Material sky;

        public float SunElevation { get; private set; }
        public float Precip { get; private set; }
        public float Cloud { get; private set; }
        public float Wind { get; private set; }
        /// 0 = pelny dzien, 1 = noc (slonce < -6 st., po zmierzchu cywilnym).
        public float Night01 { get; private set; }
        public bool IsNight => SunElevation < -4f;

        public void Init(Camera c)
        {
            cam = c;
            sun = FindSun();
            sun.type = LightType.Directional;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.75f;
            RenderSettings.sun = sun;
            var procedural = Shader.Find("Skybox/Procedural");
            if (RenderSettings.skybox != null) sky = new Material(RenderSettings.skybox);
            else if (procedural != null) sky = new Material(procedural);
            if (sky != null) RenderSettings.skybox = sky;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Exponential;
            rain = CreateRain();
            stars = CreateStars();
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
            Wind = data.HourValue(h.wind, t);

            // azymut: z grubsza 15 stopni na godzine; czas sloneczny = UTC + 21 st. dlugosci / 15 = UTC + 1,4 h
            float solarHour = (float)((data.Day.startEpoch + (long)t) % 86400) / 3600f + 1.4f;
            float azimuth = (solarHour - 12f) * 15f + 180f;
            float elev = SunElevation;
            // ponizej horyzontu: swiatlo ksiezyca z gory, zeby miasto nie bylo calkiem czarne
            bool night = elev < -4f;
            float lightElev = night ? 40f : Mathf.Max(elev, 3f);
            sun.transform.rotation = Quaternion.Euler(lightElev, night ? azimuth + 180f : azimuth, 0);

            float day = Mathf.Clamp01((elev + 6f) / 18f);          // 0 noc .. 1 dzien
            Night01 = 1f - Mathf.Clamp01((elev + 6f) / 8f);       // swiatla miasta wlaczaja sie o zmierzchu
            float cloudDim = Mathf.Lerp(1f, 0.55f, Cloud);
            sun.intensity = night ? 0.18f : Mathf.Lerp(0.3f, 1.25f, day) * cloudDim;
            sun.shadowStrength = night ? 0.3f : Mathf.Lerp(0.85f, 0.45f, Cloud);
            var warm = new Color(1f, 0.66f, 0.42f);
            sun.color = night ? new Color(0.55f, 0.65f, 1f) : Color.Lerp(warm, new Color(1f, 0.97f, 0.92f), Mathf.Clamp01(elev / 18f));

            var skyDay = new Color(0.58f, 0.66f, 0.78f); var skyNight = new Color(0.06f, 0.08f, 0.16f);
            var eqDay = new Color(0.52f, 0.54f, 0.58f); var eqNight = new Color(0.05f, 0.06f, 0.10f);
            float dim = Mathf.Lerp(1f, 0.82f, Cloud);
            RenderSettings.ambientSkyColor = Color.Lerp(skyNight, skyDay, day) * dim;
            RenderSettings.ambientEquatorColor = Color.Lerp(eqNight, eqDay, day) * dim;
            RenderSettings.ambientGroundColor = Color.Lerp(new Color(0.02f, 0.02f, 0.03f), new Color(0.22f, 0.21f, 0.2f), day);

            // zachod/wschod: cieplejsza mgla przy niskim sloncu
            var fogDay = Color.Lerp(new Color(0.64f, 0.71f, 0.80f), new Color(0.56f, 0.58f, 0.61f), Cloud);
            var fogDusk = new Color(0.62f, 0.47f, 0.40f);
            var fogNight = new Color(0.025f, 0.035f, 0.07f);
            float dusk = Mathf.Clamp01(1f - Mathf.Abs(elev - 1f) / 7f) * (1f - Cloud * 0.6f);
            var fog = Color.Lerp(fogNight, Color.Lerp(fogDay, fogDusk, dusk), day);
            RenderSettings.fogColor = fog;
            RenderSettings.fogDensity = Mathf.Lerp(0.000022f, 0.00007f, Mathf.Max(Cloud * 0.5f, Mathf.Clamp01(Precip / 1.5f)));
            if (cam)
            {
                cam.clearFlags = sky != null ? CameraClearFlags.Skybox : CameraClearFlags.SolidColor;
                cam.backgroundColor = fog;
            }
            if (sky != null)
            {
                if (sky.HasProperty("_Exposure")) sky.SetFloat("_Exposure", Mathf.Lerp(0.08f, 1.15f, day) * cloudDim);
                if (sky.HasProperty("_AtmosphereThickness")) sky.SetFloat("_AtmosphereThickness", Mathf.Lerp(0.9f, 1.25f, Cloud));
                if (sky.HasProperty("_SkyTint")) sky.SetColor("_SkyTint", Color.Lerp(new Color(0.5f, 0.5f, 0.55f), new Color(0.6f, 0.6f, 0.6f), Cloud));
                if (sky.HasProperty("_GroundColor")) sky.SetColor("_GroundColor", Color.Lerp(fogNight, new Color(0.37f, 0.36f, 0.35f), day));
            }

            // deszcz: emisja proporcjonalna do opadu, ukos wg wiatru; system podaza za kamera
            var em = rain.emission;
            em.rateOverTime = Precip > 0.05f ? Mathf.Clamp(Precip * rainPerMm, 1500f, 22000f) : 0f;
            var vel = rain.velocityOverLifetime;
            vel.x = new ParticleSystem.MinMaxCurve(Wind * 18f);
            if (cam)
            {
                var p = cam.transform.position;
                rain.transform.position = new Vector3(p.x, Mathf.Max(p.y * 0.6f, 400f), p.z) + cam.transform.forward * 600f;
                stars.transform.position = p;
            }
            // gwiazdy: tylko w nocy i przy malym zachmurzeniu (jasnosc przez kolor materialu - dziala na istniejace czasteczki)
            float sa = Night01 * Mathf.Clamp01(1.2f - Cloud * 1.1f);
            var sr = stars.GetComponent<ParticleSystemRenderer>();
            sr.enabled = sa > 0.02f;
            if (sr.enabled) Mats.SetGlowTint(sr.sharedMaterial, sa);
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
            var vel = ps.velocityOverLifetime;
            vel.enabled = true;
            vel.space = ParticleSystemSimulationSpace.World;
            vel.x = new ParticleSystem.MinMaxCurve(0f);
            vel.y = new ParticleSystem.MinMaxCurve(0f);
            vel.z = new ParticleSystem.MinMaxCurve(0f);
            var em = ps.emission;
            em.rateOverTime = 0;
            var r = go.GetComponent<ParticleSystemRenderer>();
            r.renderMode = ParticleSystemRenderMode.Stretch;
            r.velocityScale = 0.12f;
            r.lengthScale = 1f;
            r.sharedMaterial = CityBuilder.Queue(Mats.Vertex(Color.white), 3200);
            r.shadowCastingMode = ShadowCastingMode.Off;
            ps.Play();
            return ps;
        }

        /// Gwiazdy: polsfera czasteczek wokol kamery (przesuwa sie z kamera, nie obraca).
        ParticleSystem CreateStars()
        {
            var ps = Fx.GlowSystem(transform, "Stars", 1800, 1999);
            var main = ps.main;
            main.simulationSpace = ParticleSystemSimulationSpace.Local;
            var r = ps.GetComponent<ParticleSystemRenderer>();
            r.maxParticleSize = 0.01f;
            var rnd = new System.Random(7);
            var buf = new ParticleSystem.Particle[1800];
            for (int i = 0; i < buf.Length; i++)
            {
                // rownomiernie na polsferze, lekko powyzej horyzontu
                float z = 0.08f + 0.92f * (float)rnd.NextDouble();
                float a = (float)(rnd.NextDouble() * Mathf.PI * 2);
                float s = Mathf.Sqrt(1 - z * z);
                buf[i].position = new Vector3(s * Mathf.Cos(a), z, s * Mathf.Sin(a)) * 16000f;
                buf[i].startSize = 25f + 70f * (float)(rnd.NextDouble() * rnd.NextDouble());
                float warm = (float)rnd.NextDouble();
                buf[i].startColor = Color.Lerp(new Color(0.75f, 0.85f, 1f), new Color(1f, 0.9f, 0.75f), warm);
                buf[i].remainingLifetime = 1e6f;
                buf[i].startLifetime = 1e6f;
            }
            ps.SetParticles(buf, buf.Length);
            return ps;
        }
    }
}
