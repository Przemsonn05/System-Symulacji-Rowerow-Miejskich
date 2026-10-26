// Materialy tworzone w kodzie - dzialaja w Built-in Render Pipeline i w URP (domyslnie w Unity 6).
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

        public static Material Lit(Color c, float smoothness = 0.2f)
        {
            var m = new Material(IsUrp ? Find("Universal Render Pipeline/Lit", "Standard")
                                       : Find("Standard", "Universal Render Pipeline/Lit"));
            SetColor(m, c);
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", smoothness);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", smoothness);
            m.enableInstancing = true;
            return m;
        }

        public static Material Unlit(Color c)
        {
            var m = new Material(IsUrp ? Find("Universal Render Pipeline/Unlit", "Unlit/Color")
                                       : Find("Unlit/Color", "Universal Render Pipeline/Unlit"));
            SetColor(m, c);
            m.enableInstancing = true;
            return m;
        }

        /// Przezroczysty, niezalezny od swiatla (linie, slady, pierscienie). Uzywa kolorow wierzcholkow.
        public static Material Vertex(Color c)
        {
            var m = new Material(Find("Sprites/Default"));
            m.color = c;
            return m;
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

        // ------------------------------------------------------------- paleta

        public static readonly Color Background = new Color(0.06f, 0.07f, 0.09f);
        public static readonly Color Ground = new Color(0.11f, 0.12f, 0.14f);
        public static readonly Color Cycleway = new Color(0.20f, 0.85f, 0.55f, 0.55f);
        public static readonly Color Bike = new Color(1.00f, 0.80f, 0.20f);
        public static readonly Color EBike = new Color(0.30f, 0.85f, 1.00f);
        public static readonly Color Truck = new Color(1.00f, 0.42f, 0.18f);
        public static readonly Color Empty = new Color(0.95f, 0.20f, 0.25f);
        public static readonly Color Low = new Color(1.00f, 0.62f, 0.15f);
        public static readonly Color Ok = new Color(0.25f, 0.85f, 0.45f);
        public static readonly Color Full = new Color(0.30f, 0.55f, 1.00f);
        public static readonly Color Overfull = new Color(0.70f, 0.40f, 1.00f);
        public static readonly Color NoData = new Color(0.40f, 0.40f, 0.42f);

        /// Kolor stacji wg zapelnienia (rowery / pojemnosc).
        public static Color StationColor(float bikes, int cap)
        {
            if (bikes < 0) return NoData;
            if (bikes < 0.5f) return Empty;
            float fill = bikes / Mathf.Max(cap, 1);
            if (fill < 0.25f) return Color.Lerp(Empty, Low, fill / 0.25f);
            if (fill < 0.5f) return Color.Lerp(Low, Ok, (fill - 0.25f) / 0.25f);
            if (fill <= 1f) return Color.Lerp(Ok, Full, (fill - 0.5f) / 0.5f);
            return Color.Lerp(Full, Overfull, Mathf.Clamp01((fill - 1f) / 1f));
        }
    }
}
