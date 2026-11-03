// Pora dnia i pogoda z danych: pozycja slonca (wysokosc z astral / Open-Meteo), niebo, gwiazdy noca,
// zachmurzenie, cienie chmur sunace z wiatrem (cookie swiatla w URP), mgla, deszcz z wiatrem, mokre ulice.
// Night01 steruje swiatlami miasta (okna, latarnie), Wet01 - mokra nawierzchnia.
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

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
        /// 0 = sucho, 1 = mokro (deszcz teraz albo w ostatnich ok. 1,5 h; schnie stopniowo).
        public float Wet01 { get; private set; }

        // cienie chmur
        public float cloudCookieSize = 7000f;
        Texture2D cookie;
        float[] noise, noiseSorted;
        float cookieCloud = -1;
        Vector2 cookieOffset;
        float lastT = -1;
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
            // mokro: deszcz z ostatnich 2 h, starszy coraz slabiej (deterministycznie - dziala tez przy przewijaniu)
            float wet = 0;
            for (int k = 0; k <= 4; k++)
                wet = Mathf.Max(wet, Mathf.Clamp01(data.HourValue(h.precip, t - k * 1800f) / 0.3f) * (1f - k * 0.2f));
            Wet01 = wet;
            UpdateClouds(t);

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
            // URP + ACES: jasniejsze slonce; pod chmurami mniej przyciemniania - cien daja chmury (cookie)
            sun.intensity = night ? 0.18f : Mathf.Lerp(0.3f, 1.25f, day) * (Mats.IsUrp ? 1.45f * Mathf.Lerp(1f, 0.78f, Cloud) : cloudDim);
            sun.shadowStrength = night ? 0.3f : Mathf.Lerp(0.85f, 0.45f, Cloud);
            var warm = new Color(1f, 0.66f, 0.42f);
            sun.color = night ? new Color(0.55f, 0.65f, 1f) : Color.Lerp(warm, new Color(1f, 0.97f, 0.92f), Mathf.Clamp01(elev / 18f));

            var skyDay = new Color(0.58f, 0.66f, 0.78f); var skyNight = new Color(0.06f, 0.08f, 0.16f);
            var eqDay = new Color(0.52f, 0.54f, 0.58f); var eqNight = new Color(0.05f, 0.06f, 0.10f);
            float dim = Mathf.Lerp(1f, 0.82f, Cloud);
            RenderSettings.ambientSkyColor = Color.Lerp(skyNight, skyDay, day) * dim;
            RenderSettings.ambientEquatorColor = Color.Lerp(eqNight, eqDay, day) * dim;
            RenderSettings.ambientGroundColor = Color.Lerp(new Color(0.02f, 0.02f, 0.03f), new Color(0.22f, 0.21f, 0.2f), day);
            // URP bierze swiatlo otoczenia z sondy SH - zmiany kolorow w trakcie dzialania trzeba do niej przepisac
            var sh = new SphericalHarmonicsL2();
            var eq = RenderSettings.ambientEquatorColor;
            sh.AddAmbientLight(eq);
            sh.AddDirectionalLight(Vector3.up, (RenderSettings.ambientSkyColor - eq) * 1.2f, 1f);
            sh.AddDirectionalLight(Vector3.down, (RenderSettings.ambientGroundColor - eq) * 1.2f, 1f);
            RenderSettings.ambientProbe = sh;

            // zachod/wschod: cieplejsza mgla przy niskim sloncu
            var fogDay = Color.Lerp(new Color(0.64f, 0.71f, 0.80f), new Color(0.56f, 0.58f, 0.61f), Cloud);
            var fogDusk = new Color(0.62f, 0.47f, 0.40f);
            var fogNight = new Color(0.045f, 0.055f, 0.095f);
            float dusk = Mathf.Clamp01(1f - Mathf.Abs(elev - 1f) / 7f) * (1f - Cloud * 0.6f);
            var fog = Color.Lerp(fogNight, Color.Lerp(fogDay, fogDusk, dusk), day);
            RenderSettings.fogColor = fog;
            RenderSettings.fogDensity = Mathf.Lerp(0.000011f, 0.000045f, Mathf.Max(Cloud * 0.4f, Mathf.Clamp01(Precip / 1.5f)));
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

        // ---------------------------------------------------------------- cienie chmur

        void UpdateClouds(float t)
        {
            float dt = lastT < 0 ? 0 : Mathf.Clamp(t - lastT, -3600f, 3600f);
            lastT = t;
            bool on = !IsNight && Cloud > 0.08f && Cloud < 0.97f && Mats.IsUrp;
            if (!on) { if (sun.cookie != null) sun.cookie = null; return; }
            if (cookie == null) BuildNoise();
            if (Mathf.Abs(Cloud - cookieCloud) > 0.04f) FillCookie(Cloud);
            if (sun.cookie != cookie) sun.cookie = cookie;
            // chmury plyna z wiatrem (kierunek zachodni - przewazajacy w Warszawie); predkosc wiatru w m/s
            cookieOffset += new Vector2(0.85f, 0.25f) * (Mathf.Max(Wind, 5f) / 3.6f) * dt * 0.6f;
            cookieOffset.x %= cloudCookieSize; cookieOffset.y %= cloudCookieSize;
            var ld = sun.GetUniversalAdditionalLightData();
            ld.lightCookieSize = new Vector2(cloudCookieSize, cloudCookieSize);
            ld.lightCookieOffset = cookieOffset;
        }

        /// Szum fraktalny powtarzalny na brzegach (tekstura kafelkuje sie bez szwow).
        void BuildNoise()
        {
            const int n = 256;
            noise = new float[n * n];
            var rnd = new System.Random(5);
            float total = 0;
            for (int o = 0, cells = 4; o < 5; o++, cells *= 2)
            {
                float amp = Mathf.Pow(0.55f, o);
                total += amp;
                var g = new float[cells * cells];
                for (int i = 0; i < g.Length; i++) g[i] = (float)rnd.NextDouble();
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float fx = x * cells / (float)n, fy = y * cells / (float)n;
                        int x0 = (int)fx, y0 = (int)fy, x1 = (x0 + 1) % cells, y1 = (y0 + 1) % cells;
                        float sx = Mathf.SmoothStep(0, 1, fx - x0), sy = Mathf.SmoothStep(0, 1, fy - y0);
                        float a = Mathf.Lerp(g[y0 * cells + x0], g[y0 * cells + x1], sx);
                        float b = Mathf.Lerp(g[y1 * cells + x0], g[y1 * cells + x1], sx);
                        noise[y * n + x] += Mathf.Lerp(a, b, sy) * amp;
                    }
            }
            for (int i = 0; i < noise.Length; i++) noise[i] /= total;
            noiseSorted = (float[])noise.Clone();
            System.Array.Sort(noiseSorted);
            cookie = new Texture2D(n, n, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, name = "CloudShadows" };
        }

        /// Prog szumu tak, zeby chmury zakrywaly taki ulamek nieba jak zachmurzenie z Open-Meteo.
        void FillCookie(float cloud)
        {
            cookieCloud = cloud;
            float th = noiseSorted[Mathf.Clamp((int)((1 - cloud) * (noiseSorted.Length - 1)), 0, noiseSorted.Length - 1)];
            var px = new Color32[noise.Length];
            for (int i = 0; i < noise.Length; i++)
            {
                float shade = Mathf.SmoothStep(0, 1, (noise[i] - th + 0.05f) / 0.1f);   // miekkie brzegi chmur
                byte v = (byte)(255 * (1f - 0.55f * shade));
                px[i] = new Color32(v, v, v, v);
            }
            cookie.SetPixels32(px);
            cookie.Apply(true);
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
