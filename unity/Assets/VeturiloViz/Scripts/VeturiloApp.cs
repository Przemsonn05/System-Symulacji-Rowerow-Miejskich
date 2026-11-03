// Punkt wejscia: buduje cala scene w kodzie i steruje czasem symulacji.
// Wystarczy pusta scena i Play - komponent tworzy sie sam (RuntimeInitializeOnLoadMethod).
//
// Tryb zrzutow (raport, test bez klikania): aplikacja uruchomiona z argumentem
//   -vtShots <folder>   zapisuje serie zrzutow ekranu (rozne godziny, widoki, warstwy) i sie zamyka.
using System;
using System.Collections;
using System.IO;
using UnityEngine;

namespace Veturilo.Viz
{
    public class VeturiloApp : MonoBehaviour
    {
        /// Tworz scene automatycznie po nacisnieciu Play (pusta scena wystarczy).
        public static bool AutoStart = true;

        public static readonly string[] LayerNames =
            { "Budynki", "Mapa", "Drogi rower.", "Ślady", "Łuki OD", "Korki", "Mieszkańcy", "Ciężarówki", "Opisy", "Poza stacją" };

        [Header("Start")]
        public float startHour = 7f;
        public float startSpeed = 300f;

        [Header("Opisy POI")]
        public float labelScale = 0.016f;
        public float labelMaxDistance = 6500f;

        public DataStore Data { get; private set; }
        public StationLayer Stations { get; private set; }
        public BikeLayer Bikes { get; private set; }
        public TruckLayer Trucks { get; private set; }
        public FlowLayer Flows { get; private set; }
        public ContextLayer Context { get; private set; }
        public EnvironmentFx Env { get; private set; }
        public CameraRig Rig { get; private set; }
        public Hud Hud { get; private set; }
        public float Time01 => Data?.Day == null ? 0 : t / Data.Day.lengthSec;
        public bool Playing { get; private set; } = true;
        public float Speed { get; private set; } = 300f;
        public bool TourRunning => tour != null && tour.Running;

        CityBuilder city;
        Camera cam;
        Tour tour;
        float t;
        bool ready;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Boot()
        {
            if (!AutoStart || FindFirstObjectByType<VeturiloApp>() != null) return;
            new GameObject("Veturilo").AddComponent<VeturiloApp>();
        }

        void Start()
        {
            Application.targetFrameRate = 60;
            QualitySettings.shadowDistance = 7000f;
            QualitySettings.shadowCascades = 4;
            QualitySettings.antiAliasing = Mathf.Max(QualitySettings.antiAliasing, 4);
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

            Flows = new GameObject("Flows").AddComponent<FlowLayer>();
            Flows.transform.SetParent(world, false);
            Flows.Init(Data);
            Flows.gameObject.SetActive(false);

            Context = new GameObject("Context").AddComponent<ContextLayer>();
            Context.transform.SetParent(world, false);
            Context.Init(Data);

            Env = gameObject.AddComponent<EnvironmentFx>();
            Env.Init(cam);

            tour = new Tour(this);
            Hud.Build();
            Speed = startSpeed;
            LoadDay(Data.DefaultDay(), 0);
            t = Data.TimeOfLocalHour(startHour);
            ready = true;

            string shots = Arg("-vtShots");
            if (shots != null) StartCoroutine(ShotSeries(shots));
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
            cam.allowHDR = true;
            cam.allowMSAA = true;
            Rig = cam.GetComponent<CameraRig>();
            if (Rig == null) Rig = cam.gameObject.AddComponent<CameraRig>();
            View(1, instant: true);
        }

        void LoadDay(int i, float time)
        {
            if (!Data.LoadDay(i)) { Hud.ShowMessage(Data.Error); return; }
            Bikes.OnDayLoaded();
            Trucks.OnDayLoaded();
            Flows.OnDayLoaded();
            Context.OnDayLoaded();
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

            Env.UpdateAt(Data, t);
            city.SetNight(Env.Night01);
            Stations.UpdateAt(t, Env.Night01);
            Bikes.UpdateAt(t, Playing ? Speed : 1f, Playing);
            Trucks.UpdateAt(t);
            Flows.UpdateAt(t);
            Context.UpdateAt(t);
            tour.Update(t);
            HandlePointer();
            Hud.UpdateAt(Data, t);
        }

        void LateUpdate()
        {
            if (!ready || city == null) return;
            // opisy POI: zawsze przodem do kamery, staly rozmiar na ekranie, ukryte z daleka
            bool on = city.Pois.activeSelf;
            if (!on) return;
            foreach (var (tr, cat) in city.PoiLabels)
                Fx.Face(tr, cam, labelScale, cat == "metro" || cat == "train_station" ? labelMaxDistance
                                             : cat == "university" ? labelMaxDistance * 0.55f : labelMaxDistance * 0.4f);
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
            if (InputCompat.Down(K.C)) { StopTour(); Rig.cinematic = !Rig.cinematic; }
            if (InputCompat.Down(K.H)) Hud.ToggleVisible();
            if (InputCompat.Down(K.F1)) Hud.ToggleHelp();
            if (InputCompat.Down(K.V)) SetMode((ViewMode)(((int)Stations.Mode + 1) % 3));
            if (InputCompat.Down(K.T)) ToggleTour();
            if (InputCompat.Down(K.F)) ToggleLayer("Łuki OD");
            if (InputCompat.Down(K.K)) ToggleLayer("Korki");
            if (InputCompat.Down(K.P)) ToggleLayer("Mieszkańcy");
            if (InputCompat.Down(K.M)) ToggleLayer("Mapa");
            if (InputCompat.Down(K.F12)) Screenshot();
            if (InputCompat.Down(K.Escape)) { if (!Hud.CloseHelp()) Stations.Selected = null; }
            if (InputCompat.Down(K.Digit1) || InputCompat.Down(K.R)) { StopTour(); View(1); }
            if (InputCompat.Down(K.Digit2)) { StopTour(); View(2); }
            if (InputCompat.Down(K.Digit3)) { StopTour(); View(3); }
            if (InputCompat.Down(K.Digit4)) { StopTour(); View(4); }
            if (InputCompat.Down(K.Digit5)) { StopTour(); View(5); }
        }

        /// Gotowe ujecia kamery: 1 miasto, 2 Srodmiescie, 3 z gory, 4 nisko nad ulicami, 5 Wisla i mosty.
        public void View(int preset, bool instant = false)
        {
            Rig.Smoothing = 8f;
            switch (preset)
            {
                case 2: Rig.Preset(new Vector3(-300, 0, 0), 35f, 42f, 3800f, instant); break;
                case 3: Rig.Preset(new Vector3(0, 0, -600), 0f, 89f, 19000f, instant); break;
                case 4: Rig.Preset(new Vector3(-700, 0, -300), 62f, 16f, 1300f, instant); break;
                case 5: Rig.Preset(new Vector3(1700, 0, 300), 250f, 30f, 5200f, instant); break;
                default: Rig.Preset(new Vector3(0, 0, -900), 15f, 50f, 15000f, instant); break;
            }
        }

        // ------------------------------------------------------------------ akcje UI

        public void TogglePlay() { if (ready) Playing = !Playing; }
        public void SetSpeed(float s) { if (!ready) return; Speed = s; Playing = true; }
        public void Seek(float f) { if (ready) t = Mathf.Clamp01(f) * (Data.Day.lengthSec - 1); }
        public void SeekLocalHour(float hour) { if (ready) t = Data.TimeOfLocalHour(hour); }
        void Jump(float dt) { if (ready) t = Mathf.Clamp(t + dt, 0, Data.Day.lengthSec - 1); }

        public void ChangeDay(int delta)
        {
            if (!ready) return;
            int n = Data.Index.days.Length;
            LoadDay(((Data.DayIndex + delta) % n + n) % n, t);
        }

        public void SetMode(ViewMode m) { if (ready) Stations.Mode = m; }

        public void SelectStation(StationView v)
        {
            Stations.Selected = v;
            if (v != null) Rig.FocusOn(v.Root.position, 2400f);
        }

        public void ToggleTour() { if (!ready) return; if (tour.Running) StopTour(); else tour.Start(); }
        void StopTour() { if (tour != null && tour.Running) tour.Stop(); }

        public bool LayerOn(string name)
        {
            if (!ready) return false;
            switch (name)
            {
                case "Budynki": return city.Buildings.activeSelf;
                case "Mapa": return city.Basemap.activeSelf;
                case "Drogi rower.": return city.Cycleways.activeSelf;
                case "Ślady": return Bikes.showTrails;
                case "Łuki OD": return Flows.gameObject.activeSelf;
                case "Korki": return Context.TrafficOn;
                case "Mieszkańcy": return city.Population.activeSelf;
                case "Ciężarówki": return Trucks.gameObject.activeSelf;
                case "Opisy": return city.Pois.activeSelf;
                case "Poza stacją": return Bikes.showLoose;
                default: return false;
            }
        }

        public void SetLayer(string name, bool on)
        {
            if (!ready || LayerOn(name) == on) return;
            ToggleLayer(name);
        }

        public void ToggleLayer(string name)
        {
            if (!ready) return;
            bool on = !LayerOn(name);
            switch (name)
            {
                case "Budynki": city.Buildings.SetActive(on); break;
                case "Mapa": city.Basemap.SetActive(on); break;
                case "Drogi rower.": city.Cycleways.SetActive(on); break;
                case "Ślady": Bikes.SetTrails(on); break;
                case "Łuki OD": Flows.gameObject.SetActive(on); if (on) Flows.OnDayLoaded(); break;
                case "Korki": Context.SetTraffic(on); break;
                case "Mieszkańcy": city.Population.SetActive(on); break;
                case "Ciężarówki": Trucks.gameObject.SetActive(on); break;
                case "Opisy": city.Pois.SetActive(on); break;
                case "Poza stacją": Bikes.showLoose = on; break;
            }
        }

        // ------------------------------------------------------------------ zrzuty ekranu

        public static string ScreenshotDir()
        {
            // w edytorze: folder Screenshots obok Assets; w aplikacji: obok pliku .exe
            var dir = Path.Combine(Path.GetDirectoryName(Application.dataPath) ?? ".", "Screenshots");
            Directory.CreateDirectory(dir);
            return dir;
        }

        public void Screenshot()
        {
            if (!ready) return;
            string name = $"veturilo_{Data.Day.date}_{Data.ClockText(t).Replace(":", "")}_{DateTime.Now:HHmmss}.png";
            string path = Path.Combine(ScreenshotDir(), name);
            ScreenCapture.CaptureScreenshot(path);
            Hud.ShowCaption("Zapisano zrzut: " + path, 4f);
            Debug.Log("Veturilo: zrzut " + path);
        }

        static string Arg(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++) if (args[i] == name) return args[i + 1];
            return null;
        }

        /// Seria zrzutow do raportu: kazde ujecie = dzien, godzina, kamera, widok stacji, warstwy.
        IEnumerator ShotSeries(string dir)
        {
            Directory.CreateDirectory(dir);
            var shots = new (string name, float hour, int view, ViewMode mode, string[] layers)[]
            {
                ("01_miasto_rano", 8.0f, 1, ViewMode.Fill, new string[0]),
                ("02_srodmiescie_szczyt", 8.5f, 2, ViewMode.Fill, new string[0]),
                ("03_bilans_luki", 8.25f, 1, ViewMode.Balance, new[] { "Łuki OD" }),
                ("04_h2_pustki", 13f, 1, ViewMode.Problem, new string[0]),
                ("05_ulice_wieczor", 18.5f, 4, ViewMode.Fill, new string[0]),
                ("06_noc_wisla", 21f, 5, ViewMode.Fill, new string[0]),
                ("07_korki_mieszkancy", 16.5f, 1, ViewMode.Fill, new[] { "Mieszkańcy" }),
                ("08_popoludnie_srodmiescie", 16.75f, 2, ViewMode.Fill, new string[0]),
            };
            yield return null;
            foreach (var s in shots)
            {
                foreach (var l in new[] { "Łuki OD", "Mieszkańcy" }) SetLayer(l, Array.IndexOf(s.layers, l) >= 0);
                SetMode(s.mode);
                View(s.view, instant: true);
                // start 8 min wczesniej i odtwarzanie, zeby rowery mialy slady
                t = Data.TimeOfLocalHour(s.hour) - 480f;
                Speed = 320f; Playing = true;
                yield return new WaitForSecondsRealtime(1.5f);
                Playing = false;
                yield return new WaitForSecondsRealtime(0.3f);
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, s.name + ".png"));
                yield return new WaitForSecondsRealtime(0.5f);
            }

            // karta stacji (Metro Centrum, jesli jest) i poczatek pokazu z napisem
            SetLayer("Mieszkańcy", false);
            SetMode(ViewMode.Fill);
            t = Data.TimeOfLocalHour(8.5f);
            var pick = Stations.Views.Find(v => v.Info.name.Contains("Metro Centrum")) ?? Stations.Views[0];
            SelectStation(pick);
            Speed = 300f; Playing = true;
            yield return new WaitForSecondsRealtime(2.5f);
            Playing = false;
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "09_karta_stacji.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            Stations.Selected = null;
            ToggleTour();
            yield return new WaitForSecondsRealtime(4f);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "10_pokaz.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            Application.Quit();
        }
    }
}
