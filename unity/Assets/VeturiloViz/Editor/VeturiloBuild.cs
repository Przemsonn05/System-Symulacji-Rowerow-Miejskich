// Menu "Veturilo" w edytorze: scena startowa, szablony materialow (shadery w buildzie) i budowa aplikacji.
// Z wiersza polecen:  Unity.exe -batchmode -quit -projectPath unity -executeMethod Veturilo.Viz.Editor.VeturiloBuild.BatchBuild
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Veturilo.Viz.Editor
{
    public static class VeturiloBuild
    {
        const string ScenePath = "Assets/Scenes/Veturilo.unity";
        const string MaterialsDir = "Assets/VeturiloViz/Resources/VeturiloMaterials";
        const string BuildPath = "Build/Veturilo.exe";

        [MenuItem("Veturilo/Utwórz scenę", priority = 1)]
        public static void CreateScene()
        {
            EnsureMaterials();
            if (!File.Exists(ScenePath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
                var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
                EditorSceneManager.SaveScene(scene, ScenePath);
            }
            else if (!Application.isBatchMode) EditorSceneManager.OpenScene(ScenePath);
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

        /// Szablony materialow w Resources - dzieki nim shadery tworzone z kodu trafiaja do zbudowanej aplikacji.
        [MenuItem("Veturilo/Odśwież szablony materiałów", priority = 20)]
        public static void EnsureMaterials()
        {
            Directory.CreateDirectory(MaterialsDir);
            Make("Lit", "Standard", null);
            Make("Facade", "Standard", m =>
            {
                m.EnableKeyword("_EMISSION");
                m.SetColor("_EmissionColor", Color.white);
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            });
            Make("Unlit", "Unlit/Color", null);
            Make("Vertex", "Sprites/Default", null);
            Make("Glow", "Legacy Shaders/Particles/Additive", null);
            AssetDatabase.SaveAssets();
        }

        static void Make(string name, string shader, System.Action<Material> setup)
        {
            string path = $"{MaterialsDir}/{name}.mat";
            if (AssetDatabase.LoadAssetAtPath<Material>(path) != null) return;
            var s = Shader.Find(shader);
            if (s == null) { Debug.LogWarning("Veturilo: brak shadera " + shader); return; }
            var m = new Material(s);
            setup?.Invoke(m);
            AssetDatabase.CreateAsset(m, path);
        }
    }
}
