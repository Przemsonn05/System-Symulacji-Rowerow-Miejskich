// Punkt wejscia: buduje cala scene w kodzie i steruje czasem symulacji.
// Wystarczy pusta scena i Play - komponent tworzy sie sam (RuntimeInitializeOnLoadMethod).
//
// Tryb zrzutow (raport, test bez klikania): aplikacja uruchomiona z argumentem
//   -vtShots <folder>   zapisuje serie zrzutow ekranu (rozne godziny, widoki, warstwy) i sie zamyka.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Veturilo.Viz
{
    public class VeturiloApp : MonoBehaviour
    {
        /// Tworz scene automatycznie po nacisnieciu Play (pusta scena wystarczy).
        public static bool AutoStart = true;

        /// Warstwy Unity: obiekty dnia A widzi tylko lewa kamera, dnia B tylko prawa (porownanie dni).
        public const int LayerA = 8, LayerB = 9;

        public static readonly string[] LayerNames =
        {
            "Budynki", "Mapa", "Drogi rower.", "Ślady", "Ślady dnia", "Łuki OD",
            "Utracony popyt", "Korki", "Mieszkańcy", "Ciężarówki", "Opisy", "Poza stacją",
        };

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
        public DayTrailLayer Trails { get; private set; }
        public LostDemandLayer Lost { get; private set; }
        public EnvironmentFx Env { get; private set; }
        public CameraRig Rig { get; private set; }
        public Hud Hud { get; private set; }
        public CityBuilder City => city;
        public float Time01 => Data?.Day == null ? 0 : t / Data.Day.lengthSec;
        public bool Playing { get; private set; } = true;
        public float Speed { get; private set; } = 300f;
        public bool TourRunning => tour != null && tour.Running;

        // porownanie dwoch dni (podzielony ekran)
        public bool Comparing { get; private set; }
        public DataStore DataB { get; private set; }
        public StationLayer StationsB { get; private set; }
        public BikeLayer BikesB { get; private set; }
        public TruckLayer TrucksB { get; private set; }
        public float TimeB { get; private set; }
        GameObject worldB;
        Camera camB;

        // sledzenie roweru / ciezarowki
        public int FollowTrip { get; private set; } = -1;
        public int FollowTruck { get; private set; } = -1;

        CityBuilder city;
        Camera cam;
        Tour tour;
        float t;
        bool ready;
        readonly List<Rect> labelRects = new List<Rect>();

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

            Stations = Layer<StationLayer>("Stations", world, LayerA);
            Stations.Build(Data);
            Bikes = Layer<BikeLayer>("Bikes", world, LayerA);
            Bikes.Init(Data);
            Trucks = Layer<TruckLayer>("Trucks", world, LayerA);
            Trucks.Init(Data);
            Flows = Layer<FlowLayer>("Flows", world, LayerA);
            Flows.Init(Data);
            Flows.gameObject.SetActive(false);
            Trails = Layer<DayTrailLayer>("DayTrails", world, LayerA);
            Trails.Init(Data);
            Trails.gameObject.SetActive(false);
            Lost = Layer<LostDemandLayer>("LostDemand", world, LayerA);
            Lost.Init(Data);
            Lost.gameObject.SetActive(false);

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

        static T Layer<T>(string name, Transform parent, int layer) where T : Component
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            return go.AddComponent<T>();
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
            cam.cullingMask = ~(1 << LayerB);
            Rig = cam.GetComponent<CameraRig>();
            if (Rig == null) Rig = cam.gameObject.AddComponent<CameraRig>();
            View(1, instant: true);
        }

        void LoadDay(int i, float time)
        {
            if (!Data.LoadDay(i)) { Hud.ShowMessage(Data.Error); return; }
            StopFollow();
            Bikes.OnDayLoaded();
            Trucks.OnDayLoaded();
            Flows.OnDayLoaded();
            Trails.OnDayLoaded();
            Lost.OnDayLoaded();
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
            Trails.UpdateAt(t);
            Lost.UpdateAt(t);
            Context.UpdateAt(t);
            if (Comparing) UpdateCompare();
            tour.Update(t);
            UpdateFollow();
            HandlePointer();
            Hud.UpdateAt(Data, t);
        }

        void LateUpdate()
        {
            if (!ready || city == null || !city.Pois.activeSelf) return;
            // opisy POI: przodem do kamery, staly rozmiar na ekranie, ukryte z daleka i gdy nachodza na wazniejsze
            float px = 0.64f * labelScale * Screen.height / (2f * Mathf.Tan(cam.fieldOfView * 0.5f * Mathf.Deg2Rad));
            labelRects.Clear();
            foreach (var (tr, cat) in city.PoiLabels)
            {
                Fx.Face(tr, cam, labelScale, cat == "metro" || cat == "train_station" ? labelMaxDistance
                                             : cat == "university" ? labelMaxDistance * 0.55f : labelMaxDistance * 0.4f);
                if (!tr.gameObject.activeSelf) continue;
                var sp = cam.WorldToScreenPoint(tr.position);
                if (sp.z <= 0) { tr.gameObject.SetActive(false); continue; }
                var tm = tr.GetComponent<TextMesh>();
                float w = tm.text.Length * px * 0.55f;
                var rect = new Rect(sp.x - w * 0.5f - 4, sp.y - 2, w + 8, px + 4);
                bool overlap = false;
                foreach (var r in labelRects) if (r.Overlaps(rect)) { overlap = true; break; }
                if (overlap) tr.gameObject.SetActive(false);
                else labelRects.Add(rect);
            }
        }

        void HandlePointer()
        {
            Stations.Hovered = null;
            if (Rig.MouseOverUi) return;
            var mp = InputCompat.MousePosition;
            if (Comparing && mp.x > Screen.width * 0.5f) return;   // prawa polowa: tylko podglad
            var ray = cam.ScreenPointToRay(mp);
            StationView hit = null; int trip = -1, truck = -1;
            if (Physics.Raycast(ray, out var info, 100000f, 1 << LayerA))
            {
                hit = Stations.ViewOf(info.collider);
                if (hit == null) trip = Bikes.TripOf(info.collider);
                if (hit == null && trip < 0) truck = Trucks.TruckOf(info.collider);
            }
            Stations.Hovered = hit;
            if (InputCompat.MouseUp(0) && !Rig.WasDrag)
            {
                if (trip >= 0) Follow(trip, -1);
                else if (truck >= 0) Follow(-1, truck);
                else
                {
                    Stations.Selected = hit;
                    if (hit != null) { StopFollow(); Rig.FocusOn(hit.Root.position, 2400f); }
                }
            }
        }

        void HandleKeys()
        {
            bool shift = InputCompat.Held(K.Shift);
            if (InputCompat.Down(K.Space)) TogglePlay();
            if (InputCompat.Down(K.Right)) Jump(900);
            if (InputCompat.Down(K.Left)) Jump(-900);
            if (InputCompat.Down(K.RightBracket)) SetSpeed(Mathf.Min(Speed * 2f, 3600f));
            if (InputCompat.Down(K.LeftBracket)) SetSpeed(Mathf.Max(Speed / 2f, 15f));
            if (InputCompat.Down(K.Period)) { if (shift) ChangeDayB(+1); else ChangeDay(+1); }
            if (InputCompat.Down(K.Comma)) { if (shift) ChangeDayB(-1); else ChangeDay(-1); }
            if (InputCompat.Down(K.C)) { StopTour(); StopFollow(); Rig.cinematic = !Rig.cinematic; }
            if (InputCompat.Down(K.H)) Hud.ToggleVisible();
            if (InputCompat.Down(K.F1)) Hud.ToggleHelp();
            if (InputCompat.Down(K.V)) SetMode((ViewMode)(((int)Stations.Mode + 1) % 3));
            if (InputCompat.Down(K.T)) ToggleTour();
            if (InputCompat.Down(K.X)) ToggleCompare();
            if (InputCompat.Down(K.F)) ToggleLayer("Łuki OD");
            if (InputCompat.Down(K.G)) ToggleLayer("Ślady dnia");
            if (InputCompat.Down(K.U)) ToggleLayer("Utracony popyt");
            if (InputCompat.Down(K.K)) ToggleLayer("Korki");
            if (InputCompat.Down(K.P)) ToggleLayer("Mieszkańcy");
            if (InputCompat.Down(K.M)) ToggleLayer("Mapa");
            if (InputCompat.Down(K.F12)) Screenshot();
            if (InputCompat.Down(K.Escape))
            {
                if (Hud.CloseHelp()) { }
                else if (FollowTrip >= 0 || FollowTruck >= 0) StopFollow();
                else Stations.Selected = null;
            }
            if (InputCompat.Down(K.Digit1) || InputCompat.Down(K.R)) { StopTour(); View(1); }
            if (InputCompat.Down(K.Digit2)) { StopTour(); View(2); }
            if (InputCompat.Down(K.Digit3)) { StopTour(); View(3); }
            if (InputCompat.Down(K.Digit4)) { StopTour(); View(4); }
            if (InputCompat.Down(K.Digit5)) { StopTour(); View(5); }
        }

        /// Gotowe ujecia kamery: 1 miasto, 2 Srodmiescie, 3 z gory, 4 nisko nad ulicami, 5 Wisla i mosty.
        public void View(int preset, bool instant = false)
        {
            StopFollow();
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

        // ------------------------------------------------------------------ sledzenie roweru / ciezarowki

        public void Follow(int trip, int truck)
        {
            StopTour();
            FollowTrip = trip; FollowTruck = truck;
            Stations.Selected = null;
            Rig.cinematic = false;
            Rig.StartFollow(trip >= 0 ? 750f : 1100f);
        }

        public void StopFollow()
        {
            if (FollowTrip < 0 && FollowTruck < 0) return;
            FollowTrip = -1; FollowTruck = -1;
            Rig.StopFollow();
            Hud?.SetFollow(null);
        }

        void UpdateFollow()
        {
            if (FollowTrip < 0 && FollowTruck < 0) return;
            if (Rig.UserPanned) { StopFollow(); return; }
            if (FollowTrip >= 0)
            {
                var tr = Data.Day.trips; int i = FollowTrip;
                if (!Bikes.PositionOf(i, out var p))
                {
                    Hud.ShowCaption($"Rower #{tr.bike[i]} dojechał: {PlaceName(tr.toSt[i])}", 5f);
                    StopFollow();
                    return;
                }
                Rig.Track(p);
                float left = Mathf.Max(0, tr.arr[i] - t) / 60f;
                Hud.SetFollow($"<b>Rower #{tr.bike[i]}</b>{(tr.ebike[i] == 1 ? " · e-rower" : "")}\n" +
                              $"{PlaceName(tr.fromSt[i])}  →  {PlaceName(tr.toSt[i])}\n" +
                              $"<color=#9aa3b0>{tr.km[i]:0.0} km · {(tr.arr[i] - tr.dep[i]) / 60f:0} min · do celu {left:0} min · Esc – koniec</color>");
            }
            else
            {
                var tk = Data.Day.trucks; int i = FollowTruck;
                if (!Trucks.PositionOf(i, out var p))
                {
                    Hud.ShowCaption($"Ciężarówka dowiozła {tk.n[i]} rowerów: {PlaceName(tk.toSt[i])}", 5f);
                    StopFollow();
                    return;
                }
                Rig.Track(p);
                float left = Mathf.Max(0, tk.arr[i] - t) / 60f;
                Hud.SetFollow($"<b>Ciężarówka operatora · {tk.n[i]} rowerów</b>\n" +
                              $"{PlaceName(tk.fromSt[i])}  →  {PlaceName(tk.toSt[i])}\n" +
                              $"<color=#9aa3b0>relokacja · do celu {left:0} min · Esc – koniec</color>");
            }
        }

        string PlaceName(int st) => st >= 0 && st < Data.Stations.Length ? Data.Stations[st].name : "miejsce poza stacją";

        // ------------------------------------------------------------------ porownanie dwoch dni

        public void ToggleCompare()
        {
            if (!ready) return;
            if (Comparing) { ExitCompare(); return; }
            StopTour();
            if (DataB == null)
            {
                DataB = new DataStore(Data);
                worldB = new GameObject("WorldB") { layer = LayerB };
                worldB.transform.SetParent(transform, false);
                StationsB = Layer<StationLayer>("StationsB", worldB.transform, LayerB);
                StationsB.Build(DataB);
                BikesB = Layer<BikeLayer>("BikesB", worldB.transform, LayerB);
                BikesB.Init(DataB);
                TrucksB = Layer<TruckLayer>("TrucksB", worldB.transform, LayerB);
                TrucksB.Init(DataB);
                var go = new GameObject("CameraB");
                camB = go.AddComponent<Camera>();
                go.AddComponent<CameraMirror>().source = cam;
            }
            if (!LoadDayB(PickDayB())) return;
            Comparing = true;
            worldB.SetActive(true);
            camB.enabled = true;
            camB.cullingMask = ~(1 << LayerA);
            cam.rect = new Rect(0, 0, 0.5f, 1);
            camB.rect = new Rect(0.5f, 0, 0.5f, 1);
            Hud.SetCompare(true);
        }

        void ExitCompare()
        {
            Comparing = false;
            if (worldB != null) worldB.SetActive(false);
            if (camB != null) camB.enabled = false;
            cam.rect = new Rect(0, 0, 1, 1);
            Hud.SetCompare(false);
        }

        /// Dzien do porownania: dla dnia roboczego ostatni pelny dzien wolny, dla wolnego - ostatni pelny roboczy.
        int PickDayB()
        {
            var days = Data.Index.days;
            bool workA = days[Data.DayIndex].dayType == "workday";
            for (int i = days.Length - 1; i >= 0; i--)
                if (i != Data.DayIndex && days[i].coverage >= 0.95f && (days[i].dayType == "workday") != workA) return i;
            return (Data.DayIndex + 1) % days.Length;
        }

        bool LoadDayB(int i)
        {
            if (!DataB.LoadDay(i)) { Hud.ShowCaption(DataB.Error, 5f); return false; }
            BikesB.OnDayLoaded();
            TrucksB.OnDayLoaded();
            return true;
        }

        public void ChangeDayB(int delta)
        {
            if (!Comparing) return;
            int n = Data.Index.days.Length;
            LoadDayB(((DataB.DayIndex + delta) % n + n) % n);
        }

        void UpdateCompare()
        {
            // ta sama godzina lokalna w obu dniach (dzien zmiany czasu ma 25 h)
            TimeB = DataB.TimeOfLocalHour(Data.LocalHour(t));
            StationsB.Mode = Stations.Mode;
            StationsB.UpdateAt(TimeB, Env.Night01);
            BikesB.showTrails = Bikes.showTrails;
            BikesB.showLoose = Bikes.showLoose;
            BikesB.UpdateAt(TimeB, Playing ? Speed : 1f, Playing);
            TrucksB.gameObject.SetActive(Trucks.gameObject.activeSelf);
            TrucksB.UpdateAt(TimeB);
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
            StopFollow();
            Stations.Selected = v;
            if (v != null) Rig.FocusOn(v.Root.position, 2400f);
        }

        public void ToggleTour() { if (!ready) return; if (tour.Running) StopTour(); else { if (Comparing) ExitCompare(); StopFollow(); tour.Start(); } }
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
                case "Ślady dnia": return Trails.gameObject.activeSelf;
                case "Łuki OD": return Flows.gameObject.activeSelf;
                case "Utracony popyt": return Lost.gameObject.activeSelf;
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
                case "Ślady dnia": Trails.gameObject.SetActive(on); break;
                case "Łuki OD": Flows.gameObject.SetActive(on); if (on) Flows.OnDayLoaded(); break;
                case "Utracony popyt": Lost.gameObject.SetActive(on); if (on) Lost.OnDayLoaded(); break;
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

        /// Seria zrzutow do raportu: kazde ujecie = godzina, kamera, widok stacji, warstwy.
        IEnumerator ShotSeries(string dir)
        {
            Directory.CreateDirectory(dir);
            var optional = new[] { "Łuki OD", "Mieszkańcy", "Ślady dnia", "Utracony popyt" };
            var shots = new (string name, float hour, int view, ViewMode mode, string[] layers)[]
            {
                ("01_miasto_rano", 8.0f, 1, ViewMode.Fill, new string[0]),
                ("02_srodmiescie_szczyt", 8.5f, 2, ViewMode.Fill, new string[0]),
                ("03_bilans_luki", 8.25f, 1, ViewMode.Balance, new[] { "Łuki OD" }),
                ("04_h2_pustki", 13f, 1, ViewMode.Problem, new string[0]),
                ("05_utracony_popyt", 17.5f, 1, ViewMode.Fill, new[] { "Utracony popyt" }),
                ("06_ulice_wieczor", 18.5f, 4, ViewMode.Fill, new string[0]),
                ("07_noc_wisla", 21f, 5, ViewMode.Fill, new string[0]),
                ("08_slady_dnia", 22.5f, 1, ViewMode.Fill, new[] { "Ślady dnia" }),
                ("09_mieszkancy", 16.5f, 1, ViewMode.Fill, new[] { "Mieszkańcy" }),
            };
            yield return null;
            foreach (var s in shots)
            {
                foreach (var l in optional) SetLayer(l, Array.IndexOf(s.layers, l) >= 0);
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
            foreach (var l in optional) SetLayer(l, false);
            SetMode(ViewMode.Fill);

            // karta stacji (Metro Centrum, jesli jest)
            t = Data.TimeOfLocalHour(8.5f);
            var pick = Stations.Views.Find(v => v.Info.name.Contains("Metro Centrum")) ?? Stations.Views[0];
            SelectStation(pick);
            Speed = 300f; Playing = true;
            yield return new WaitForSecondsRealtime(2.5f);
            Playing = false;
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "10_karta_stacji.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            Stations.Selected = null;

            // sledzenie roweru: najdluzszy przejazd trwajacy o 8:20
            t = Data.TimeOfLocalHour(8.33f);
            Playing = true; Speed = 60f;
            yield return new WaitForSecondsRealtime(0.3f);
            var tr = Data.Day.trips; int best = -1; float bestKm = 0;
            for (int i = 0; i < tr.dep.Length; i++)
                if (tr.dep[i] <= t && tr.arr[i] > t + 600 && tr.km[i] > bestKm && Bikes.PositionOf(i, out _)) { best = i; bestKm = tr.km[i]; }
            if (best >= 0) Follow(best, -1);
            yield return new WaitForSecondsRealtime(3f);
            Playing = false;
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "11_sledzenie_roweru.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            StopFollow();

            // porownanie dwoch dni
            View(2, instant: true);
            t = Data.TimeOfLocalHour(8.4f);
            ToggleCompare();
            Speed = 300f; Playing = true;
            yield return new WaitForSecondsRealtime(1.5f);
            Playing = false;
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "12_porownanie_dni.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            ToggleCompare();

            ToggleTour();
            yield return new WaitForSecondsRealtime(4f);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "13_pokaz.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            Application.Quit();
        }
    }

    /// Druga kamera (porownanie dni): kopiuje polozenie i ustawienia glownej po jej aktualizacji.
    [DefaultExecutionOrder(1000)]
    public class CameraMirror : MonoBehaviour
    {
        public Camera source;
        Camera self;

        void LateUpdate()
        {
            if (source == null) return;
            if (self == null) self = GetComponent<Camera>();
            transform.SetPositionAndRotation(source.transform.position, source.transform.rotation);
            self.fieldOfView = source.fieldOfView;
            self.nearClipPlane = source.nearClipPlane;
            self.farClipPlane = source.farClipPlane;
            self.clearFlags = source.clearFlags;
            self.backgroundColor = source.backgroundColor;
            self.allowHDR = source.allowHDR;
            self.allowMSAA = source.allowMSAA;
        }
    }
}
