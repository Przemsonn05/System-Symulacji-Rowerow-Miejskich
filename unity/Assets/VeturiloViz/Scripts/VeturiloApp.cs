// Punkt wejscia: buduje cala scene w kodzie i steruje czasem symulacji.
// Wystarczy pusta scena i Play - komponent tworzy sie sam (RuntimeInitializeOnLoadMethod).
using UnityEngine;

namespace Veturilo.Viz
{
    public class VeturiloApp : MonoBehaviour
    {
        /// Tworz scene automatycznie po nacisnieciu Play (pusta scena wystarczy).
        public static bool AutoStart = true;

        [Header("Start")]
        public float startHour = 7f;
        public float startSpeed = 300f;

        [Header("Opisy POI")]
        public float labelScale = 0.03f;
        public float labelMaxDistance = 9000f;

        public DataStore Data { get; private set; }
        public StationLayer Stations { get; private set; }
        public BikeLayer Bikes { get; private set; }
        public TruckLayer Trucks { get; private set; }
        public EnvironmentFx Env { get; private set; }
        public CameraRig Rig { get; private set; }
        public Hud Hud { get; private set; }
        public float Time01 => Data?.Day == null ? 0 : t / Data.Day.lengthSec;
        public bool Playing { get; private set; } = true;
        public float Speed { get; private set; } = 300f;

        CityBuilder city;
        Camera cam;
        float t;
        bool ready;
        bool showLabels = true;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (!AutoStart || FindFirstObjectByType<VeturiloApp>() != null) return;
            new GameObject("Veturilo").AddComponent<VeturiloApp>();
        }

        void Start()
        {
            Application.targetFrameRate = 60;
            QualitySettings.shadowDistance = 6000f;
            SetupCamera();

            Hud = new Hud(this);
            Data = new DataStore();
            if (!Data.Load())
            {
                Env = gameObject.AddComponent<EnvironmentFx>();
                Hud.Build();
                Hud.ShowMessage(Data.Error);
                return;
            }

            var world = new GameObject("World").transform;
            world.SetParent(transform, false);
            city = new CityBuilder();
            city.Build(Data, world);

            Stations = new GameObject("Stations").AddComponent<StationLayer>();
            Stations.transform.SetParent(world, false);
            Stations.Build(Data);

            Bikes = new GameObject("Bikes").AddComponent<BikeLayer>();
            Bikes.transform.SetParent(world, false);
            Bikes.Init(Data);

            Trucks = new GameObject("Trucks").AddComponent<TruckLayer>();
            Trucks.transform.SetParent(world, false);
            Trucks.Init(Data);

            Env = gameObject.AddComponent<EnvironmentFx>();
            Env.Init(cam);

            Hud.Build();
            Speed = startSpeed;
            LoadDay(Data.DefaultDay(), startHour * 3600f);
            ready = true;
        }

        void SetupCamera()
        {
            cam = Camera.main;
            if (cam == null)
            {
                var go = new GameObject("Main Camera");
                go.tag = "MainCamera";
                cam = go.AddComponent<Camera>();
                go.AddComponent<AudioListener>();
            }
            cam.nearClipPlane = 5f;
            cam.farClipPlane = 80000f;
            cam.fieldOfView = 50f;
            Rig = cam.GetComponent<CameraRig>();
            if (Rig == null) Rig = cam.gameObject.AddComponent<CameraRig>();
            Rig.Preset(new Vector3(0, 0, -600), 15f, 52f, 13000f, instant: true);
        }

        void LoadDay(int i, float time)
        {
            if (!Data.LoadDay(i)) { Hud.ShowMessage(Data.Error); return; }
            Bikes.OnDayLoaded();
            Trucks.OnDayLoaded();
            Hud.OnDayLoaded(Data);
            t = Mathf.Clamp(time, 0, Data.Day.lengthSec - 1);
        }

        // ------------------------------------------------------------------ petla

        void Update()
        {
            if (!ready) return;
            HandleKeys();

            if (Playing)
            {
                t += Time.unscaledDeltaTime * Speed;
                if (t >= Data.Day.lengthSec)
                {
                    // koniec dnia: nastepny dzien (albo od poczatku, jesli to ostatni)
                    int next = Data.DayIndex + 1 < Data.Index.days.Length ? Data.DayIndex + 1 : 0;
                    LoadDay(next, 0);
                }
            }

            Stations.UpdateAt(t);
            Bikes.UpdateAt(t, Playing ? Speed : 1f);
            Trucks.UpdateAt(t);
            Env.UpdateAt(Data, t);
            HandlePointer();
            Hud.UpdateAt(Data, t);
        }

        void LateUpdate()
        {
            if (!ready || city == null) return;
            // opisy POI: zawsze przodem do kamery, staly rozmiar na ekranie, ukryte z daleka
            var cp = cam.transform.position;
            bool on = showLabels && city.Pois.activeSelf;
            foreach (var (tr, cat) in city.PoiLabels)
            {
                float d = Vector3.Distance(cp, tr.position);
                float max = cat == "metro" || cat == "train_station" ? labelMaxDistance : labelMaxDistance * 0.6f;
                bool vis = on && d < max;
                if (tr.gameObject.activeSelf != vis) tr.gameObject.SetActive(vis);
                if (!vis) continue;
                tr.rotation = cam.transform.rotation;
                tr.localScale = Vector3.one * (d * labelScale);
            }
        }

        void HandlePointer()
        {
            Stations.Hovered = null;
            if (Rig.MouseOverUi) return;
            var ray = cam.ScreenPointToRay(InputCompat.MousePosition);
            StationView hit = null;
            if (Physics.Raycast(ray, out var info, 100000f)) hit = Stations.ViewOf(info.collider);
            Stations.Hovered = hit;
            if (InputCompat.MouseUp(0) && !Rig.WasDrag)
            {
                Stations.Selected = hit;
                if (hit != null) Rig.FocusOn(hit.Root.position, 2400f);
            }
        }

        void HandleKeys()
        {
            if (InputCompat.Down(K.Space)) TogglePlay();
            if (InputCompat.Down(K.Right)) Jump(900);
            if (InputCompat.Down(K.Left)) Jump(-900);
            if (InputCompat.Down(K.RightBracket)) SetSpeed(Mathf.Min(Speed * 2f, 3600f));
            if (InputCompat.Down(K.LeftBracket)) SetSpeed(Mathf.Max(Speed / 2f, 15f));
            if (InputCompat.Down(K.Period)) ChangeDay(+1);
            if (InputCompat.Down(K.Comma)) ChangeDay(-1);
            if (InputCompat.Down(K.C)) Rig.cinematic = !Rig.cinematic;
            if (InputCompat.Down(K.H)) Hud.ToggleVisible();
            if (InputCompat.Down(K.F1)) Hud.ToggleHelp();
            if (InputCompat.Down(K.Escape)) { if (!Hud.CloseHelp()) Stations.Selected = null; }
            if (InputCompat.Down(K.Digit1) || InputCompat.Down(K.R)) Rig.Preset(new Vector3(0, 0, -600), 15f, 52f, 13000f);
            if (InputCompat.Down(K.Digit2)) Rig.Preset(new Vector3(-300, 0, 0), 35f, 42f, 3800f);
            if (InputCompat.Down(K.Digit3)) Rig.Preset(new Vector3(0, 0, -600), 0f, 89f, 17000f);
            if (InputCompat.Down(K.Digit4)) Rig.Preset(new Vector3(-600, 0, -400), 60f, 18f, 1300f);
        }

        // ------------------------------------------------------------------ akcje UI

        public void TogglePlay() { if (ready) Playing = !Playing; }
        public void SetSpeed(float s) { if (!ready) return; Speed = s; Playing = true; }
        public void Seek(float f) { if (ready) t = Mathf.Clamp01(f) * (Data.Day.lengthSec - 1); }
        void Jump(float dt) { if (ready) t = Mathf.Clamp(t + dt, 0, Data.Day.lengthSec - 1); }

        public void ChangeDay(int delta)
        {
            if (!ready) return;
            int n = Data.Index.days.Length;
            LoadDay(((Data.DayIndex + delta) % n + n) % n, t);
        }

        public void ToggleLayer(string name)
        {
            if (!ready) return;
            GameObject go = null;
            bool on;
            switch (name)
            {
                case "Budynki": go = city.Buildings; break;
                case "Drogi rower.": go = city.Cycleways; break;
                case "Ciężarówki": go = Trucks.gameObject; break;
                case "Opisy": go = city.Pois; break;
                case "Ślady":
                    Bikes.SetTrails(!Bikes.showTrails);
                    Hud.SetLayerButton(name, Bikes.showTrails);
                    return;
            }
            if (go == null) return;
            on = !go.activeSelf;
            go.SetActive(on);
            Hud.SetLayerButton(name, on);
        }
    }
}
