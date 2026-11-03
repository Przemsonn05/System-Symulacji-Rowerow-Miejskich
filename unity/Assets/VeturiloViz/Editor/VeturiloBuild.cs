// Menu "Veturilo" w edytorze: potok renderowania URP (bloom, SSAO, cienie), scena startowa,
// szablony materialow (shadery w buildzie) i budowa aplikacji.
// Z wiersza polecen:  Unity.exe -batchmode -quit -projectPath unity -executeMethod Veturilo.Viz.Editor.VeturiloBuild.BatchBuild
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Veturilo.Viz.Editor
{
    public static class VeturiloBuild
    {
        const string ScenePath = "Assets/Scenes/Veturilo.unity";
        const string MaterialsDir = "Assets/VeturiloViz/Resources/VeturiloMaterials";
        const string SettingsDir = "Assets/VeturiloViz/Settings";
        const string UrpPath = SettingsDir + "/VeturiloURP.asset";
        const string BuildPath = "Build/Veturilo.exe";

        [MenuItem("Veturilo/Utwórz scenę", priority = 1)]
        public static void CreateScene()
        {
            SetupUrp();
            EnsureMaterials();
            if (!File.Exists(ScenePath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
                var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                EditorSceneManager.SaveScene(scene, ScenePath);
            }
            var sc = EditorSceneManager.OpenScene(ScenePath);
            // mgla wlaczona juz w scenie - inaczej build usuwa warianty shaderow z mgla (dalekie podloze bylo czarne)
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Exponential;
            RenderSettings.fogDensity = 0.00003f;
            EditorSceneManager.MarkSceneDirty(sc);
            EditorSceneManager.SaveScene(sc);
            var gs = new SerializedObject(AssetDatabase.LoadAssetAtPath<Object>("ProjectSettings/GraphicsSettings.asset"));
            gs.FindProperty("m_FogStripping").intValue = 1;   // wlasne: zachowaj wszystkie tryby mgly
            gs.FindProperty("m_FogKeepLinear").boolValue = true;
            gs.FindProperty("m_FogKeepExp").boolValue = true;
            gs.FindProperty("m_FogKeepExp2").boolValue = true;
            gs.ApplyModifiedPropertiesWithoutUndo();
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log("Veturilo: scena " + ScenePath + " gotowa - naciśnij Play.");
        }

        [MenuItem("Veturilo/Zbuduj aplikację (Windows)", priority = 2)]
        public static void Build()
        {
            CreateScene();
            PlayerSettings.productName = "Veturilo 3D";
            PlayerSettings.companyName = "Symulacja Veturilo";
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1920;
            PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.runInBackground = true;
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = BuildPath,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            });
            Debug.Log($"Veturilo: build {report.summary.result}, {report.summary.totalErrors} błędów -> {Path.GetFullPath(BuildPath)}");
            if (!Application.isBatchMode && report.summary.result == UnityEditor.Build.Reporting.BuildResult.Succeeded)
                EditorUtility.RevealInFinder(BuildPath);
        }

        /// Wiersz polecen: tworzy scene i buduje aplikacje; kod wyjscia != 0 przy bledzie.
        public static void BatchBuild()
        {
            Build();
            if (!File.Exists(BuildPath)) EditorApplication.Exit(1);
        }

        /// Potok URP: HDR, MSAA 4x, cienie do 7 km (4 kaskady, miekkie), SSAO; ustawiony jako domyslny.
        [MenuItem("Veturilo/Ustaw URP (bloom, cienie, SSAO)", priority = 21)]
        public static void SetupUrp()
        {
            var asset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(UrpPath);
            if (asset == null)
            {
                Directory.CreateDirectory(SettingsDir);
                // tak samo jak menu Assets > Create > Rendering > URP Asset (metoda jest wewnetrzna w URP)
                var create = typeof(UniversalRenderPipelineAsset).GetMethod("CreateRendererAsset", BindingFlags.NonPublic | BindingFlags.Static);
                var data = (UniversalRendererData)create.Invoke(null, new object[]
                    { SettingsDir + "/VeturiloURP_Renderer.asset", RendererType.UniversalRenderer, false, "Renderer" });

                var ssao = ScriptableObject.CreateInstance<ScreenSpaceAmbientOcclusion>();
                ssao.name = "SSAO";
                AssetDatabase.AddObjectToAsset(ssao, data);
                var so = new SerializedObject(ssao);
                so.FindProperty("m_Settings.Intensity").floatValue = 1.4f;
                so.FindProperty("m_Settings.Radius").floatValue = 5f;
                so.FindProperty("m_Settings.DirectLightingStrength").floatValue = 0.2f;
                so.FindProperty("m_Settings.Falloff").floatValue = 4000f;
                so.FindProperty("m_Settings.Downsample").boolValue = true;
                so.ApplyModifiedPropertiesWithoutUndo();
                AssetDatabase.TryGetGUIDAndLocalFileIdentifier(ssao, out _, out long localId);
                var dso = new SerializedObject(data);
                var feats = dso.FindProperty("m_RendererFeatures");
                feats.InsertArrayElementAtIndex(feats.arraySize);
                feats.GetArrayElementAtIndex(feats.arraySize - 1).objectReferenceValue = ssao;
                var map = dso.FindProperty("m_RendererFeatureMap");
                map.InsertArrayElementAtIndex(map.arraySize);
                map.GetArrayElementAtIndex(map.arraySize - 1).longValue = localId;
                dso.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(data);

                asset = UniversalRenderPipelineAsset.Create(data);
                AssetDatabase.CreateAsset(asset, UrpPath);
            }
            asset.supportsHDR = true;
            asset.msaaSampleCount = 4;
            asset.shadowDistance = 7000f;
            asset.shadowCascadeCount = 4;
            asset.mainLightShadowmapResolution = 4096;
            asset.supportsCameraDepthTexture = false;
            asset.supportsCameraOpaqueTexture = false;
            var aso = new SerializedObject(asset);
            var soft = aso.FindProperty("m_SoftShadowsSupported");
            if (soft != null) soft.boolValue = true;
            aso.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(asset);

            GraphicsSettings.defaultRenderPipeline = asset;
            // poziomy jakosci bez wlasnego potoku uzywaja domyslnego
            int current = QualitySettings.GetQualityLevel();
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = null;
            }
            QualitySettings.SetQualityLevel(current, false);
            AssetDatabase.SaveAssets();
        }

        /// Szablony materialow w Resources - dzieki nim shadery tworzone z kodu trafiaja do zbudowanej aplikacji.
        [MenuItem("Veturilo/Odśwież szablony materiałów", priority = 20)]
        public static void EnsureMaterials()
        {
            Directory.CreateDirectory(MaterialsDir);
            Make("Lit", "Universal Render Pipeline/Lit", m => m.enableInstancing = true);
            Make("Facade", "Universal Render Pipeline/Lit", m =>
            {
                m.EnableKeyword("_EMISSION");
                m.SetColor("_EmissionColor", Color.white);
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            });
            Make("Unlit", "Universal Render Pipeline/Unlit", null);
            Make("Vertex", "Sprites/Default", null);
            Make("Glow", "Legacy Shaders/Particles/Additive", null);
            Make("DayTrails", "Veturilo/DayTrails", null);
            Make("Water", "Veturilo/Water", null);
            AssetDatabase.SaveAssets();
        }

        static void Make(string name, string shader, System.Action<Material> setup)
        {
            string path = $"{MaterialsDir}/{name}.mat";
            var s = Shader.Find(shader);
            if (s == null) { Debug.LogWarning("Veturilo: brak shadera " + shader); return; }
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null)
            {
                // istniejacego szablonu nie ruszamy - zmiana shadera kasuje slowa kluczowe (np. _EMISSION okien),
                // a od nich zalezy, ktore warianty shadera trafia do aplikacji
                if (existing.shader == s) return;
                existing.shader = s;
                setup?.Invoke(existing);
                EditorUtility.SetDirty(existing);
                return;
            }
            var m = new Material(s);
            setup?.Invoke(m);
            AssetDatabase.CreateAsset(m, path);
        }
    }
}
