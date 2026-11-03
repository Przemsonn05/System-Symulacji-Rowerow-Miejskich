// Budowanie interfejsu (uGUI) w kodzie - bez prefabow, scena dziala po samym nacisnieciu Play.
using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem.UI;
#endif

namespace Veturilo.Viz
{
    public static class Ui
    {
        public static readonly Color PanelBg = new Color(0.04f, 0.05f, 0.07f, 0.84f);
        public static readonly Color Accent = new Color(1.00f, 0.80f, 0.20f);
        public static readonly Color TextMain = new Color(0.94f, 0.95f, 0.97f);
        public static readonly Color TextDim = new Color(0.62f, 0.66f, 0.72f);
        public static readonly Color ButtonBg = new Color(0.16f, 0.18f, 0.22f, 0.95f);
        public static readonly Color ButtonOn = new Color(0.95f, 0.72f, 0.15f, 0.95f);

        static Font _font;
        public static Font DefaultFont
        {
            get
            {
                if (_font != null) return _font;
                foreach (var name in new[] { "LegacyRuntime.ttf", "Arial.ttf" })
                {
                    try { _font = Resources.GetBuiltinResource<Font>(name); } catch (Exception) { _font = null; }
                    if (_font != null) break;
                }
                if (_font == null) _font = Font.CreateDynamicFontFromOSFont(new[] { "Arial", "Helvetica", "DejaVu Sans" }, 16);
                return _font;
            }
        }

        public static Canvas CreateCanvas(Transform parent)
        {
            var go = new GameObject("HUD", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            go.transform.SetParent(parent, false);
            var c = go.GetComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            c.sortingOrder = 10;
            var s = go.GetComponent<CanvasScaler>();
            s.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            s.referenceResolution = new Vector2(1920, 1080);
            s.matchWidthOrHeight = 0.5f;
            EnsureEventSystem();
            return c;
        }

        static void EnsureEventSystem()
        {
            if (UnityEngine.Object.FindFirstObjectByType<EventSystem>() != null) return;
            var es = new GameObject("EventSystem", typeof(EventSystem));
#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
            // modul dodany z kodu w czesci wersji Input System nie ma domyslnych akcji
            // (przyciski nie reaguja na klikniecia) - przypisujemy je jawnie
            es.AddComponent<InputSystemUIInputModule>().AssignDefaultActions();
#else
            es.AddComponent<StandaloneInputModule>();
#endif
        }

        public static RectTransform Rect(string name, Transform parent, Vector2 anchorMin, Vector2 anchorMax,
                                         Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = go.GetComponent<RectTransform>();
            r.anchorMin = anchorMin; r.anchorMax = anchorMax; r.pivot = pivot;
            r.anchoredPosition = pos; r.sizeDelta = size;
            return r;
        }

        /// Panel z tlem i cienkim paskiem akcentu u gory.
        public static RectTransform Panel(string name, Transform parent, Vector2 anchor, Vector2 pos, Vector2 size,
                                          Color? bg = null, bool accent = true)
        {
            var r = Rect(name, parent, anchor, anchor, anchor, pos, size);
            var img = r.gameObject.AddComponent<Image>();
            img.color = bg ?? PanelBg;
            if (accent)
            {
                var strip = Rect("Accent", r, new Vector2(0, 1), new Vector2(1, 1), new Vector2(0.5f, 1), Vector2.zero, new Vector2(0, 3));
                var si = strip.gameObject.AddComponent<Image>();
                si.color = new Color(Accent.r, Accent.g, Accent.b, 0.85f);
                si.raycastTarget = false;
            }
            return r;
        }

        public static Text Label(Transform parent, string text, int size, Vector2 pos, Vector2 box,
                                 TextAnchor align = TextAnchor.UpperLeft, Color? color = null, FontStyle style = FontStyle.Normal)
        {
            var r = Rect("Text", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), pos, box);
            var t = r.gameObject.AddComponent<Text>();
            t.font = DefaultFont;
            t.fontSize = size;
            t.fontStyle = style;
            t.alignment = align;
            t.color = color ?? TextMain;
            t.text = text;
            t.supportRichText = true;
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            t.raycastTarget = false;
            return t;
        }

        public static Image Swatch(Transform parent, Color c, Vector2 pos, Vector2 size)
        {
            var r = Rect("Swatch", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), pos, size);
            var img = r.gameObject.AddComponent<Image>();
            img.color = c;
            img.raycastTarget = false;
            return img;
        }

        public static Button Button(Transform parent, string text, Vector2 pos, Vector2 size, Action onClick,
                                    int fontSize = 18, TextAnchor align = TextAnchor.MiddleCenter)
        {
            var r = Rect("Button_" + text, parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), pos, size);
            var img = r.gameObject.AddComponent<Image>();
            img.color = ButtonBg;
            var b = r.gameObject.AddComponent<Button>();
            var colors = b.colors;
            colors.highlightedColor = new Color(1.25f, 1.25f, 1.25f);
            colors.pressedColor = new Color(0.8f, 0.8f, 0.8f);
            b.colors = colors;
            b.onClick.AddListener(() => onClick());
            var t = Label(r, text, fontSize, Vector2.zero, size, align);
            t.rectTransform.anchorMin = Vector2.zero; t.rectTransform.anchorMax = Vector2.one;
            t.rectTransform.pivot = new Vector2(0.5f, 0.5f);
            t.rectTransform.anchoredPosition = Vector2.zero;
            t.rectTransform.sizeDelta = align == TextAnchor.MiddleCenter ? Vector2.zero : new Vector2(-16, 0);
            return b;
        }

        public static void SetOn(Button b, bool on)
        {
            b.GetComponent<Image>().color = on ? ButtonOn : ButtonBg;
            var t = b.GetComponentInChildren<Text>();
            if (t) t.color = on ? Color.black : TextMain;
        }

        public static void SetText(Button b, string text)
        {
            var t = b.GetComponentInChildren<Text>();
            if (t) t.text = text;
        }

        public static Slider Slider(Transform parent, Vector2 pos, Vector2 size, Action<float> onChange)
        {
            var root = Rect("Slider", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), pos, size);
            var bg = Rect("Background", root, new Vector2(0, 0.35f), new Vector2(1, 0.65f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            bg.gameObject.AddComponent<Image>().color = new Color(1, 1, 1, 0.12f);
            var fillArea = Rect("Fill Area", root, new Vector2(0, 0.35f), new Vector2(1, 0.65f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            var fill = Rect("Fill", fillArea, Vector2.zero, new Vector2(0, 1), new Vector2(0, 0.5f), Vector2.zero, Vector2.zero);
            fill.gameObject.AddComponent<Image>().color = new Color(Accent.r, Accent.g, Accent.b, 0.55f);
            var handleArea = Rect("Handle Slide Area", root, Vector2.zero, Vector2.one, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(-16, 0));
            var handle = Rect("Handle", handleArea, new Vector2(0, 0), new Vector2(0, 1), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(16, 0));
            var himg = handle.gameObject.AddComponent<Image>();
            himg.color = Accent;
            var s = root.gameObject.AddComponent<Slider>();
            s.fillRect = fill; s.handleRect = handle; s.targetGraphic = himg;
            s.direction = UnityEngine.UI.Slider.Direction.LeftToRight;
            s.minValue = 0; s.maxValue = 1;
            s.onValueChanged.AddListener(v => onChange(v));
            return s;
        }
    }

    /// Prosty wykres slupkowy: podswietlony biezacy slupek, przyszlosc przyciemniona.
    public class BarChart
    {
        readonly Image[] bars;
        readonly RectTransform area;
        readonly Color[] colors;
        readonly Color highlight;
        float[] values = new float[0];

        public RectTransform Area => area;

        public BarChart(Transform parent, Vector2 pos, Vector2 size, int n, Color normal, Color highlight, bool background = true)
        {
            this.highlight = highlight;
            area = Ui.Rect("Chart", parent, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 1), pos, size);
            var bg = area.gameObject.AddComponent<Image>();
            bg.color = background ? new Color(1, 1, 1, 0.04f) : new Color(0, 0, 0, 0);
            bg.raycastTarget = false;
            bars = new Image[n];
            colors = new Color[n];
            float w = size.x / n;
            for (int i = 0; i < n; i++)
            {
                var r = Ui.Rect("Bar", area, Vector2.zero, Vector2.zero, Vector2.zero, new Vector2(i * w + 1, 0), new Vector2(Mathf.Max(w - 2, 1), 0));
                bars[i] = r.gameObject.AddComponent<Image>();
                bars[i].color = normal;
                bars[i].raycastTarget = false;
                colors[i] = normal;
            }
        }

        /// Wlasne kolory slupkow (np. na przemian wypozyczenia / zwroty).
        public void SetColors(Func<int, Color> color)
        {
            for (int i = 0; i < bars.Length; i++) { colors[i] = color(i); bars[i].color = colors[i]; }
        }

        public void SetValues(float[] v, float max = -1)
        {
            values = v;
            if (max <= 0) { max = 1; foreach (var x in v) max = Mathf.Max(max, x); }
            float h = area.sizeDelta.y;
            for (int i = 0; i < bars.Length; i++)
            {
                float val = i < v.Length ? Mathf.Max(v[i], 0) : 0;
                bars[i].rectTransform.sizeDelta = new Vector2(bars[i].rectTransform.sizeDelta.x, h * Mathf.Min(val / max, 1f));
            }
        }

        /// idx - slupek biezacy (jasniejszy); upTo - slupki dalej sa przyciemnione (przyszlosc).
        public void SetHighlight(int idx, int upTo = -1, int idx2 = -1)
        {
            for (int i = 0; i < bars.Length; i++)
            {
                var c = i == idx || i == idx2 ? Color.Lerp(colors[i], highlight, 0.6f) : colors[i];
                if (upTo >= 0 && i > upTo) c.a *= 0.3f;
                bars[i].color = c;
            }
        }
    }
}
