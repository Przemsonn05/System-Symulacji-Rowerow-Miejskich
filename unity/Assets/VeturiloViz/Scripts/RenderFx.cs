// Efekty URP: post-processing (bloom, tonemapping ACES, korekcja koloru, winieta) sterowany pora dnia i pogoda,
// odbicie lustrzane miasta w wodzie (osobna kamera renderowana do tekstury).
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Veturilo.Viz
{
    public class PostFx : MonoBehaviour
    {
        Volume volume;
        Bloom bloom;
        ColorAdjustments color;
        Vignette vignette;
        public bool Active => volume != null && volume.enabled;

        public static PostFx Create(Transform parent, params Camera[] cams)
        {
            var go = new GameObject("PostFx");
            go.transform.SetParent(parent, false);
            var fx = go.AddComponent<PostFx>();
            fx.Build();
            foreach (var c in cams) Enable(c);
            return fx;
        }

        public static void Enable(Camera c)
        {
            if (c == null) return;
            var d = c.GetUniversalAdditionalCameraData();
            d.renderPostProcessing = true;
            d.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
            d.antialiasingQuality = AntialiasingQuality.High;
        }

        void Build()
        {
            volume = gameObject.AddComponent<Volume>();
            volume.isGlobal = true;
            volume.priority = 10;
            var profile = ScriptableObject.CreateInstance<VolumeProfile>();
            volume.sharedProfile = profile;

            bloom = profile.Add<Bloom>(true);
            bloom.threshold.Override(0.95f);
            bloom.intensity.Override(0.6f);
            bloom.scatter.Override(0.72f);
            bloom.highQualityFiltering.Override(true);

            var tone = profile.Add<Tonemapping>(true);
            tone.mode.Override(TonemappingMode.ACES);

            color = profile.Add<ColorAdjustments>(true);
            color.postExposure.Override(0.25f);
            color.contrast.Override(12f);
            color.saturation.Override(10f);

            vignette = profile.Add<Vignette>(true);
            vignette.intensity.Override(0.22f);
            vignette.smoothness.Override(0.45f);
        }

        /// Noca mocniejsza poswiata (swiatla miasta), w deszczu chlodniejszy i mniej nasycony obraz.
        public void UpdateAt(float night01, float precip, float cloud)
        {
            if (bloom == null) return;
            bloom.intensity.value = Mathf.Lerp(0.45f, 1.5f, night01);
            bloom.threshold.value = Mathf.Lerp(1.05f, 0.85f, night01);
            float wet = Mathf.Clamp01(precip / 1.5f);
            color.saturation.value = Mathf.Lerp(12f, -8f, Mathf.Max(wet, cloud * 0.4f));
            color.postExposure.value = Mathf.Lerp(0.55f, 0.45f, night01);
            color.colorFilter.value = Color.Lerp(Color.white, new Color(0.88f, 0.94f, 1f), wet);
            vignette.intensity.value = Mathf.Lerp(0.2f, 0.32f, night01);
        }

        public void SetEnabled(bool on) { if (volume != null) volume.enabled = on; }
    }

    /// Odbicie w wodzie: kamera lustrzana wzgledem plaszczyzny wody, renderowana do tekstury o polowie rozdzielczosci.
    [DefaultExecutionOrder(2000)]
    public class PlanarReflection : MonoBehaviour
    {
        public Camera source;
        public Material water;
        public float planeY;
        public int layerMask = ~0;

        Camera rc;
        RenderTexture rt;

        public static PlanarReflection Create(Transform parent, Camera source, Material water, float planeY, int waterLayer)
        {
            var go = new GameObject("WaterReflection");
            go.transform.SetParent(parent, false);
            var pr = go.AddComponent<PlanarReflection>();
            pr.source = source; pr.water = water; pr.planeY = planeY;
            pr.layerMask = ~((1 << waterLayer) | (1 << 5) | (1 << VeturiloApp.LayerB));   // bez wody, UI i dnia B
            return pr;
        }

        void OnDisable()
        {
            if (water != null) water.SetFloat("_HasReflection", 0);
        }

        void LateUpdate()
        {
            if (source == null || water == null) return;
            int w = Mathf.Max(Screen.width / 2, 64), h = Mathf.Max(Screen.height / 2, 64);
            if (rt == null || rt.width != w || rt.height != h)
            {
                if (rt != null) rt.Release();
                rt = new RenderTexture(w, h, 24, RenderTextureFormat.DefaultHDR) { name = "WaterReflection" };
                water.SetTexture("_ReflectionTex", rt);
            }
            if (rc == null)
            {
                rc = gameObject.AddComponent<Camera>();
                rc.enabled = false;
                var d = rc.GetUniversalAdditionalCameraData();
                d.renderShadows = false;
                d.renderPostProcessing = false;
                d.requiresDepthTexture = false;
                d.requiresColorTexture = false;
            }
            rc.CopyFrom(source);
            rc.rect = new Rect(0, 0, 1, 1);
            rc.cullingMask = layerMask;
            rc.targetTexture = rt;
            rc.farClipPlane = Mathf.Min(source.farClipPlane, 30000f);

            // odbicie wzgledem plaszczyzny y = planeY
            var plane = new Vector4(0, 1, 0, -planeY);
            var r = Reflection(plane);
            rc.worldToCameraMatrix = source.worldToCameraMatrix * r;
            var p = source.transform.position;
            rc.transform.position = new Vector3(p.x, 2 * planeY - p.y, p.z);
            // skosna plaszczyzna przyciecia: nic spod wody nie trafia do odbicia
            var clip = CameraSpacePlane(rc.worldToCameraMatrix, new Vector3(0, planeY + 0.5f, 0), Vector3.up);
            rc.projectionMatrix = source.CalculateObliqueMatrix(clip);

            var req = new UniversalRenderPipeline.SingleCameraRequest { destination = rt };
            if (!RenderPipeline.SupportsRenderRequest(rc, req)) return;
            GL.invertCulling = true;
            RenderPipeline.SubmitRenderRequest(rc, req);
            GL.invertCulling = false;
            water.SetFloat("_HasReflection", 1);
        }

        static Vector4 CameraSpacePlane(Matrix4x4 worldToCamera, Vector3 pos, Vector3 normal)
        {
            var cp = worldToCamera.MultiplyPoint(pos);
            var cn = worldToCamera.MultiplyVector(normal).normalized;
            return new Vector4(cn.x, cn.y, cn.z, -Vector3.Dot(cp, cn));
        }

        static Matrix4x4 Reflection(Vector4 p)
        {
            var m = Matrix4x4.identity;
            m.m00 = 1 - 2 * p.x * p.x; m.m01 = -2 * p.x * p.y; m.m02 = -2 * p.x * p.z; m.m03 = -2 * p.w * p.x;
            m.m10 = -2 * p.y * p.x; m.m11 = 1 - 2 * p.y * p.y; m.m12 = -2 * p.y * p.z; m.m13 = -2 * p.w * p.y;
            m.m20 = -2 * p.z * p.x; m.m21 = -2 * p.z * p.y; m.m22 = 1 - 2 * p.z * p.z; m.m23 = -2 * p.w * p.z;
            return m;
        }

        void OnDestroy() { if (rt != null) rt.Release(); }
    }
}
