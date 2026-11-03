// Materialy i tekstury tworzone w kodzie. Szablony z Resources/VeturiloMaterials (tworzy je menu
// Veturilo -> Utworz scene) gwarantuja, ze shadery trafia do zbudowanej aplikacji; w edytorze
// wystarczy Shader.Find. Dziala w Built-in Render Pipeline, w URP awaryjnie (bez poswiaty).
using UnityEngine;
using UnityEngine.Rendering;

namespace Veturilo.Viz
{
    public static class Mats
    {
        static bool? _urp;
        public static bool IsUrp => _urp ??= GraphicsSettings.currentRenderPipeline != null;

        static Shader Find(params string[] names)
        {
            foreach (var n in names)
            {
                var s = Shader.Find(n);
                if (s != null) return s;
            }
            Debug.LogWarning("Veturilo: nie znaleziono shadera " + string.Join(", ", names));
            return Shader.Find("Sprites/Default");
        }

        /// Kopia szablonu z Resources (jesli jest) albo nowy material z shaderem.
        static Material New(string template, params string[] shaders)
        {
            var t = Resources.Load<Material>("VeturiloMaterials/" + template);
            return t != null && !IsUrp ? new Material(t) : new Material(Find(shaders));
        }

        public static Material Lit(Color c, float smoothness = 0.2f)
        {
            var m = IsUrp ? new Material(Find("Universal Render Pipeline/Lit", "Standard"))
                          : New("Lit", "Standard");
            SetColor(m, c);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", smoothness);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smoothness);
            if (m.HasProperty("_Metallic")) m.SetFloat("_Metallic", 0f);
            m.enableInstancing = true;
            return m;
        }

        /// Sciany budynkow: tekstura elewacji + okna swiecace noca (emisja sterowana z EnvironmentFx).
        public static Material Facade(Color tint, Texture2D albedo, Texture2D windows)
        {
            var m = IsUrp ? new Material(Find("Universal Render Pipeline/Lit", "Standard"))
                          : New("Facade", "Standard");
            SetColor(m, tint);
            if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", albedo);
            if (m.HasProperty("_BaseMap")) m.SetTexture("_BaseMap", albedo);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", 0.35f);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.35f);
            if (m.HasProperty("_EmissionMap"))
            {
                m.SetTexture("_EmissionMap", windows);
                m.SetColor("_EmissionColor", Color.black);
                m.EnableKeyword("_EMISSION");
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            }
            return m;
        }

        public static Material Unlit(Color c)
        {
            var m = IsUrp ? new Material(Find("Universal Render Pipeline/Unlit", "Unlit/Color"))
                          : New("Unlit", "Unlit/Color");
            SetColor(m, c);
            m.enableInstancing = true;
            return m;
        }

        /// Przezroczysty, niezalezny od swiatla (linie, slady, pierscienie). Uzywa kolorow wierzcholkow.
        public static Material Vertex(Color c)
        {
            var m = New("Vertex", "Sprites/Default");
            m.color = c;
            return m;
        }

        /// Slady calego dnia: linie rozszerzane w shaderze (staly rozmiar na ekranie), widoczne od chwili przejazdu.
        public static Material DayTrails()
        {
            var t = Resources.Load<Material>("VeturiloMaterials/DayTrails");
            if (t != null) return new Material(t);
            var s = Shader.Find("Veturilo/DayTrails");
            return s != null ? new Material(s) : Vertex(Color.white);
        }

        /// Addytywna poswiata (rowery, swiatla, gwiazdy) - tekstura miekkiego kola.
        public static Material Glow()
        {
            var m = IsUrp ? new Material(Find("Universal Render Pipeline/Particles/Unlit", "Sprites/Default"))
                          : New("Glow", "Legacy Shaders/Particles/Additive", "Mobile/Particles/Additive", "Sprites/Default");
            if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", GlowTexture);
            if (m.HasProperty("_BaseMap")) m.SetTexture("_BaseMap", GlowTexture);
            if (m.HasProperty("_TintColor")) m.SetColor("_TintColor", new Color(0.5f, 0.5f, 0.5f, 0.5f));
            return m;
        }

        /// Jasnosc materialu poswiaty (0..1) - mnozy kolor czasteczek, takze juz istniejacych.
        public static void SetGlowTint(Material m, float k)
        {
            if (m.HasProperty("_TintColor")) m.SetColor("_TintColor", new Color(0.5f * k, 0.5f * k, 0.5f * k, 0.5f * k));
            else SetColor(m, new Color(k, k, k, k));
        }

        public static void SetColor(Material m, Color c)
        {
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
            if (m.HasProperty("_Color")) m.SetColor("_Color", c);
        }

        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly int ColorId = Shader.PropertyToID("_Color");

        public static void SetColor(MaterialPropertyBlock b, Color c)
        {
            b.SetColor(BaseColorId, c);
            b.SetColor(ColorId, c);
        }

        // ------------------------------------------------------------- tekstury

        static Texture2D _glow;
        public static Texture2D GlowTexture
        {
            get
            {
                if (_glow != null) return _glow;
                const int n = 64;
                _glow = new Texture2D(n, n, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp, name = "Glow" };
                for (int y = 0; y < n; y++)
                    for (int x = 0; x < n; x++)
                    {
                        float d = new Vector2(x - n / 2 + 0.5f, y - n / 2 + 0.5f).magnitude / (n / 2f);
                        float core = Mathf.Clamp01(1 - d / 0.22f);
                        float halo = Mathf.Pow(Mathf.Clamp01(1 - d), 2.6f);
                        float a = Mathf.Clamp01(core + halo * 0.75f);
                        _glow.SetPixel(x, y, new Color(1, 1, 1, a));
                    }
                _glow.Apply();
                return _glow;
            }
        }

        /// Elewacja: 16 okien x 16 kondygnacji na teksture (1 okno = 4 m szerokosci, 3,3 m wysokosci).
        public const float FacadeTileU = 64f, FacadeTileV = 52.8f;
        static Texture2D _facade, _windows;

        public static Texture2D FacadeTexture { get { if (_facade == null) BuildFacade(); return _facade; } }
        public static Texture2D WindowsTexture { get { if (_windows == null) BuildFacade(); return _windows; } }

        static void BuildFacade()
        {
            const int cells = 16, px = 16, n = cells * px;
            _facade = new Texture2D(n, n, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, name = "Facade", anisoLevel = 4 };
            _windows = new Texture2D(n, n, TextureFormat.RGBA32, true) { wrapMode = TextureWrapMode.Repeat, name = "Windows", anisoLevel = 4 };
            var rnd = new System.Random(1944);
            var wall = new Color(0.86f, 0.86f, 0.84f);
            var glass = new Color(0.30f, 0.36f, 0.44f);
            for (int cy = 0; cy < cells; cy++)
                for (int cx = 0; cx < cells; cx++)
                {
                    // ok. 30% okien swieci wieczorem, w roznych odcieniach (zarowki, swietlowki, ekrany)
                    double r = rnd.NextDouble();
                    Color lit = r < 0.18 ? new Color(1f, 0.78f, 0.45f) : r < 0.27 ? new Color(1f, 0.9f, 0.7f)
                              : r < 0.31 ? new Color(0.7f, 0.85f, 1f) : Color.black;
                    float shade = 0.9f + 0.2f * (float)rnd.NextDouble();
                    for (int y = 0; y < px; y++)
                        for (int x = 0; x < px; x++)
                        {
                            bool win = x >= 3 && x <= 12 && y >= 4 && y <= 12;
                            var c = win ? glass * shade : wall;
                            if (!win && y < 2) c *= 0.85f; // pas miedzy kondygnacjami
                            _facade.SetPixel(cx * px + x, cy * px + y, c);
                            _windows.SetPixel(cx * px + x, cy * px + y, win ? lit : Color.black);
                        }
                }
            _facade.Apply(true);
            _windows.Apply(true);
        }

        // ------------------------------------------------------------- paleta

        public static readonly Color Background = new Color(0.06f, 0.07f, 0.09f);
        public static readonly Color Ground = new Color(0.17f, 0.175f, 0.19f);
        public static readonly Color Water = new Color(0.10f, 0.20f, 0.32f);
        public static readonly Color Green = new Color(0.20f, 0.32f, 0.18f);
        public static readonly Color Forest = new Color(0.12f, 0.22f, 0.12f);
        public static readonly Color Cycleway = new Color(0.20f, 0.85f, 0.55f, 0.55f);
        public static readonly Color Bike = new Color(1.00f, 0.80f, 0.20f);
        public static readonly Color EBike = new Color(0.30f, 0.85f, 1.00f);
        public static readonly Color Truck = new Color(1.00f, 0.42f, 0.18f);
        public static readonly Color Empty = new Color(0.95f, 0.20f, 0.25f);
        public static readonly Color Low = new Color(1.00f, 0.62f, 0.15f);
        public static readonly Color Ok = new Color(0.25f, 0.85f, 0.45f);
        public static readonly Color Full = new Color(0.35f, 0.62f, 0.95f);
        public static readonly Color Overfull = new Color(0.78f, 0.38f, 1.00f);
        public static readonly Color NoData = new Color(0.40f, 0.40f, 0.42f);
        public static readonly Color Losing = new Color(1.00f, 0.33f, 0.30f);    // stacja traci rowery
        public static readonly Color Gaining = new Color(0.25f, 0.75f, 1.00f);   // stacja zyskuje rowery
        public static readonly Color Neutral = new Color(0.55f, 0.57f, 0.62f);
        public static readonly Color Event = new Color(1.00f, 0.85f, 0.35f);

        /// Kolor stacji wg zapelnienia (rowery / pojemnosc). Na Veturilo 3.0 zostawianie rowerow ponad stojaki
        /// jest normalne, wiec do 150% stacja jest po prostu "pelna"; fiolet dopiero przy mocnym przepelnieniu.
        public static Color StationColor(float bikes, int cap)
        {
            if (bikes < 0) return NoData;
            if (bikes < 0.5f) return Empty;
            float fill = bikes / Mathf.Max(cap, 1);
            if (fill < 0.25f) return Color.Lerp(Empty, Low, fill / 0.25f);
            if (fill < 0.5f) return Color.Lerp(Low, Ok, (fill - 0.25f) / 0.25f);
            if (fill <= 1f) return Color.Lerp(Ok, Full, (fill - 0.5f) / 0.5f);
            if (fill <= 1.5f) return Full;
            return Color.Lerp(Full, Overfull, Mathf.Clamp01((fill - 1.5f) / 0.5f));
        }

        /// Kolor bilansu: ujemny (wiecej wypozyczen) czerwony, dodatni (wiecej zwrotow) niebieski.
        public static Color BalanceColor(int net)
        {
            if (net == 0) return Neutral;
            float k = Mathf.Clamp01(Mathf.Abs(net) / 8f);
            return Color.Lerp(Neutral, net < 0 ? Losing : Gaining, 0.35f + 0.65f * k);
        }

        /// Kolor stacji w widoku H2 wg pozycji w rankingu czasu pustki (0 = najczesciej pusta).
        public static Color ProblemColor(float rank, float shareEmpty)
        {
            if (shareEmpty <= 0) return new Color(0.28f, 0.42f, 0.34f);
            if (rank < 0.1f) return Empty;
            if (rank < 0.2f) return Low;
            return Color.Lerp(new Color(0.85f, 0.78f, 0.35f), new Color(0.35f, 0.5f, 0.4f), Mathf.InverseLerp(0.2f, 1f, rank));
        }

        /// Korki: zielony (plynnie) -> zolty -> czerwony (> 40% spowolnienia).
        public static Color CongestionColor(float c)
        {
            if (c < 0) return NoData;
            if (c < 0.15f) return Color.Lerp(Ok, new Color(1f, 0.85f, 0.2f), c / 0.15f);
            return Color.Lerp(new Color(1f, 0.85f, 0.2f), Empty, Mathf.Clamp01((c - 0.15f) / 0.25f));
        }

        /// Mieszkancy w heksagonie (~0,7 km2): ciemny granat -> fiolet -> pomarancz.
        public static Color PopulationColor(int pop)
        {
            float k = Mathf.Clamp01(Mathf.Log10(Mathf.Max(pop, 1)) / 4.3f); // 20 000 os. = 1
            var a = new Color(0.12f, 0.16f, 0.42f); var b = new Color(0.62f, 0.25f, 0.62f); var c = new Color(1f, 0.62f, 0.25f);
            return k < 0.6f ? Color.Lerp(a, b, k / 0.6f) : Color.Lerp(b, c, (k - 0.6f) / 0.4f);
        }
    }
}
