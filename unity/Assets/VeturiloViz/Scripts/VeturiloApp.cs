// Punkt wejscia: buduje cala scene w kodzie i steruje czasem symulacji.
// Wystarczy pusta scena i Play - komponent tworzy sie sam (RuntimeInitializeOnLoadMethod).
//
// Tryb zrzutow (raport, test bez klikania): aplikacja uruchomiona z argumentem
//   -vtShots <folder>   zapisuje serie zrzutow ekranu (rozne godziny, widoki, warstwy) i sie zamyka.
//
// Porownania (podzielony ekran): X - dzien rzeczywisty | symulacja tego dnia (albo inny dzien),
// Z - do 4 strategii relokacji obok siebie (przebiegi symulacji tej samej daty), N - glowny widok: dane / model.
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

        /// Warstwy Unity: obiekty glownego widoku (A) widzi tylko glowna kamera, kazdy dodatkowy panel
        /// porownania ma swoja warstwe (B, C, D) i swoja kamere.
        public const int LayerA = 8, LayerB = 9, LayerC = 10, LayerD = 11;
        static readonly int[] PanelLayers = { LayerB, LayerC, LayerD };

        public static readonly string[] LayerNames =
        {
            "Budynki", "Mapa", "Drogi rower.", "Ślady", "Ślady dnia", "Łuki OD",
            "Utracony popyt", "Korki", "Mieszkańcy", "Ciężarówki", "Opisy", "Poza stacją", "Efekty",
            "Agenci", "Fale pustek", "Ciśnienie", "Dyspozytor",
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
        public AgentLayer Agents { get; private set; }
        public CascadeLayer Cascades { get; private set; }
        public PressureLayer Pressure { get; private set; }
        public EnvironmentFx Env { get; private set; }
        public PostFx Post { get; private set; }
        public PlanarReflection Reflection { get; private set; }
        public CameraRig Rig { get; private set; }
        public Hud Hud { get; private set; }
        public CityBuilder City => city;
        public float Time01 => Data?.Day == null ? 0 : t / Data.Day.lengthSec;
        public bool Playing { get; private set; } = true;
        public float Speed { get; private set; } = 300f;
        public bool TourRunning => tour != null && tour.Running;

        // porownanie (podzielony ekran): panele dodatkowe B, C, D
        public class Panel
        {
            public DataStore Data;
            public StationLayer Stations;
            public BikeLayer Bikes;
            public TruckLayer Trucks;
            public AgentLayer Agents;
            public CascadeLayer Cascades;
            public PressureLayer Pressure;
            public GameObject World;
            public Camera Cam;
            public int Layer;
            public float Time;
        }

        public enum CompareMode { None, Pair, Strategies }
        public CompareMode Mode { get; private set; } = CompareMode.None;
        public bool Comparing => Mode != CompareMode.None;
        public readonly List<Panel> Panels = new List<Panel>();   // aktywne panele dodatkowe (bez glownego)
        readonly List<Panel> panelPool = new List<Panel>();
        int restoreEntry = -1;                                      // wpis glownego widoku sprzed trybu strategii
        // zgodnosc ze starszym kodem (Hud, pokaz): pierwszy panel dodatkowy
        public DataStore DataB => Panels.Count > 0 ? Panels[0].Data : null;
        public BikeLayer BikesB => Panels.Count > 0 ? Panels[0].Bikes : null;
        public float TimeB => Panels.Count > 0 ? Panels[0].Time : 0;

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
            Agents = Layer<AgentLayer>("Agents", world, LayerA);
            Agents.Init(Data);
            Cascades = Layer<CascadeLayer>("Cascades", world, LayerA);
            Cascades.Init(Data);
            Pressure = Layer<PressureLayer>("Pressure", world, LayerA);
            Pressure.Init(Data);
            Pressure.gameObject.SetActive(false);

            Context = new GameObject("Context").AddComponent<ContextLayer>();
            Context.transform.SetParent(world, false);
            Context.Init(Data);

            Env = gameObject.AddComponent<EnvironmentFx>();
            Env.Init(cam);
            if (Mats.IsUrp)
            {
                Post = PostFx.Create(transform, cam);
                if (city.WaterMaterial != null && city.WaterMaterial.shader.name == "Veturilo/Water")
                    Reflection = PlanarReflection.Create(transform, cam, city.WaterMaterial, CityBuilder.WaterY, 4);
            }

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
            cam.cullingMask = ~((1 << LayerB) | (1 << LayerC) | (1 << LayerD));
            Rig = cam.GetComponent<CameraRig>();
            if (Rig == null) Rig = cam.gameObject.AddComponent<CameraRig>();
            View(1, instant: true);
        }

        void LoadDay(int i, float time) => LoadEntry(i, time);

        /// Glowny widok: wpis = dzien rzeczywisty (0..dni-1) albo przebieg symulacji (dni..).
        void LoadEntry(int e, float time)
        {
            if (!Data.LoadEntry(e)) { Hud.ShowCaption(Data.Error, 5f); return; }
            StopFollow();
            Bikes.OnDayLoaded();
            Trucks.OnDayLoaded();
            Flows.OnDayLoaded();
            Trails.OnDayLoaded();
            Lost.OnDayLoaded();
            Agents.OnDayLoaded();
            Pressure.OnDayLoaded();
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
                    // koniec dnia: nastepny dzien (albo od poczatku); symulacja i porownanie - ten sam dzien od nowa
                    if (Data.IsSim || Comparing) t = 0;
                    else LoadDay(Data.DayIndex + 1 < Data.Index.days.Length ? Data.DayIndex + 1 : 0, 0);
                }
            }

            Env.UpdateAt(Data, t);
            city.SetNight(Env.Night01);
            city.SetWet(Env.Wet01);
            if (Post != null) Post.UpdateAt(Env.Night01, Env.Precip, Env.Cloud);
            Stations.UpdateAt(t, Env.Night01);
            Bikes.UpdateAt(t, Playing ? Speed : 1f, Playing);
            Trucks.UpdateAt(t);
            Flows.UpdateAt(t);
            Trails.UpdateAt(t);
            Lost.UpdateAt(t);
            Agents.UpdateAt(t, Env.Night01);
            Cascades.UpdateAt(t);
            Pressure.UpdateAt(t);
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
            if (Comparing && !cam.pixelRect.Contains(mp)) return;   // panele dodatkowe: tylko podglad
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
            if (InputCompat.Down(K.Z)) ToggleStrategies();
            if (InputCompat.Down(K.N)) ToggleModel();
            if (InputCompat.Down(K.J)) ToggleLayer("Agenci");
            if (InputCompat.Down(K.B)) ToggleLayer("Fale pustek");
            if (InputCompat.Down(K.Y)) ToggleLayer("Ciśnienie");
            if (InputCompat.Down(K.O)) ToggleLayer("Dyspozytor");
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
                string who = Data.IsSim ? $"Ciężarówka {(tk.truck != null && tk.truck.Length > i ? tk.truck[i] + 1 : 1)} (model)" : "Ciężarówka operatora";
                Hud.SetFollow($"<b>{who} · {tk.n[i]} rowerów</b>\n" +
                              $"{PlaceName(tk.fromSt[i])}  →  {PlaceName(tk.toSt[i])}\n" +
                              $"<color=#9aa3b0>relokacja · do celu {left:0} min · Esc – koniec</color>");
            }
        }

        string PlaceName(int st) => st >= 0 && st < Data.Stations.Length ? Data.Stations[st].name : "miejsce poza stacją";

        // ------------------------------------------------------------------ porownanie (podzielony ekran)

        /// X: dzien rzeczywisty | symulacja tego dnia (gdy jest), inaczej dzien innego typu.
        public void ToggleCompare()
        {
            if (!ready) return;
            if (Mode == CompareMode.Pair) { ExitCompare(); return; }
            if (Mode == CompareMode.Strategies) ExitCompare();
            StopTour();
            SetPanels(1);
            if (!LoadPanel(Panels[0], PickEntryB())) { ExitCompare(); return; }
            Mode = CompareMode.Pair;
            Layout();
            Hud.SetCompare(true);
        }

        /// Z: do 4 strategii relokacji obok siebie (przebiegi symulacji tej samej daty, jak glowny dzien).
        public void ToggleStrategies()
        {
            if (!ready) return;
            if (Mode == CompareMode.Strategies) { ExitCompare(); return; }
            if (Data.SimCount == 0) { Hud.ShowCaption("Brak symulacji – uruchom: python -m src.viz.export_sim ...", 5f); return; }
            if (Mode == CompareMode.Pair) ExitCompare();
            StopTour();
            var sims = Data.SimsOfDate(Data.Day.date);
            if (sims.Count == 0) sims = Data.SimsOfDate(Data.Index.sims[0].date);
            if (sims.Count > 4) sims = sims.GetRange(0, 4);
            float hour = Data.LocalHour(t);
            restoreEntry = Data.EntryIndex;
            LoadEntry(Data.Index.days.Length + sims[0], 0);
            t = Data.TimeOfLocalHour(hour);
            SetPanels(sims.Count - 1);
            for (int k = 1; k < sims.Count; k++) LoadPanel(Panels[k - 1], Data.Index.days.Length + sims[k]);
            Mode = sims.Count > 1 ? CompareMode.Strategies : CompareMode.None;
            Layout();
            Hud.SetCompare(Comparing);
            if (!Comparing) Hud.ShowCaption("Tylko jeden przebieg symulacji dla tej daty – pokazuję go w głównym widoku.", 5f);
        }

        /// N: glowny widok przelacza sie miedzy dniem rzeczywistym i przebiegami symulacji tej samej daty.
        public void ToggleModel()
        {
            if (!ready) return;
            if (Mode == CompareMode.Strategies) ExitCompare();
            var sims = Data.SimsOfDate(Data.Day.date);
            if (sims.Count == 0 && Data.SimCount > 0 && !Data.IsSim) sims = Data.SimsOfDate(Data.Index.sims[0].date);
            if (sims.Count == 0) { Hud.ShowCaption("Brak symulacji dla tego dnia – uruchom python -m src.viz.export_sim", 5f); return; }
            float hour = Data.LocalHour(t);
            int pos = Data.IsSim ? sims.IndexOf(Data.SimIndex) : -1;
            if (pos + 1 < sims.Count) LoadEntry(Data.Index.days.Length + sims[pos + 1], 0);
            else LoadEntry(Data.DayIndex >= 0 ? Data.DayIndex : Data.DefaultDay(), 0);
            t = Data.TimeOfLocalHour(hour);
            Hud.ShowCaption(Data.IsSim ? $"Model: {Data.SourceLabel.Replace("MODEL · ", "")} – N: kolejny przebieg / powrót do danych"
                                       : "Dane rzeczywiste – N: model tego dnia", 3.5f);
        }

        void ExitCompare()
        {
            bool strategies = Mode == CompareMode.Strategies;
            Mode = CompareMode.None;
            SetPanels(0);
            cam.rect = new Rect(0, 0, 1, 1);
            Hud.SetCompare(false);
            if (strategies && restoreEntry >= 0)
            {
                float hour = Data.LocalHour(t);
                LoadEntry(restoreEntry, 0);
                t = Data.TimeOfLocalHour(hour);
            }
            restoreEntry = -1;
        }

        /// Ustawia liczbe aktywnych paneli dodatkowych (tworzy brakujace, wylacza nadmiarowe).
        void SetPanels(int n)
        {
            while (panelPool.Count < n) panelPool.Add(CreatePanel(PanelLayers[panelPool.Count]));
            Panels.Clear();
            for (int k = 0; k < panelPool.Count; k++)
            {
                bool on = k < n;
                panelPool[k].World.SetActive(on);
                panelPool[k].Cam.enabled = on;
                if (on) Panels.Add(panelPool[k]);
            }
        }

        Panel CreatePanel(int layer)
        {
            var p = new Panel { Layer = layer, Data = new DataStore(Data) };
            p.World = new GameObject("World" + layer) { layer = layer };
            p.World.transform.SetParent(transform, false);
            p.Stations = Layer<StationLayer>("Stations", p.World.transform, layer);
            p.Stations.Build(p.Data);
            p.Bikes = Layer<BikeLayer>("Bikes", p.World.transform, layer);
            p.Bikes.Init(p.Data);
            p.Trucks = Layer<TruckLayer>("Trucks", p.World.transform, layer);
            p.Trucks.Init(p.Data);
            p.Agents = Layer<AgentLayer>("Agents", p.World.transform, layer);
            p.Agents.Init(p.Data);
            p.Cascades = Layer<CascadeLayer>("Cascades", p.World.transform, layer);
            p.Cascades.Init(p.Data);
            p.Pressure = Layer<PressureLayer>("Pressure", p.World.transform, layer);
            p.Pressure.Init(p.Data);
            var go = new GameObject("Camera" + layer);
            p.Cam = go.AddComponent<Camera>();
            go.AddComponent<CameraMirror>().source = cam;
            int others = 0;
            foreach (var l in PanelLayers) if (l != layer) others |= 1 << l;
            p.Cam.cullingMask = ~((1 << LayerA) | others);
            if (Post != null) PostFx.Enable(p.Cam);
            return p;
        }

        bool LoadPanel(Panel p, int entry)
        {
            if (!p.Data.LoadEntry(entry)) { Hud.ShowCaption(p.Data.Error, 5f); return false; }
            p.Bikes.OnDayLoaded();
            p.Trucks.OnDayLoaded();
            p.Agents.OnDayLoaded();
            p.Pressure.OnDayLoaded();
            return true;
        }

        /// Uklad ekranu: 2 panele obok siebie, 3 w kolumnach, 4 w cwiartkach (glowny zawsze lewy / lewy gorny).
        void Layout()
        {
            int n = Panels.Count + 1;
            var rects = n == 2 ? new[] { new Rect(0, 0, 0.5f, 1), new Rect(0.5f, 0, 0.5f, 1) }
                      : n == 3 ? new[] { new Rect(0, 0, 1 / 3f, 1), new Rect(1 / 3f, 0, 1 / 3f, 1), new Rect(2 / 3f, 0, 1 / 3f, 1) }
                      : n == 4 ? new[] { new Rect(0, 0.5f, 0.5f, 0.5f), new Rect(0.5f, 0.5f, 0.5f, 0.5f), new Rect(0, 0, 0.5f, 0.5f), new Rect(0.5f, 0, 0.5f, 0.5f) }
                      : new[] { new Rect(0, 0, 1, 1) };
            cam.rect = rects[0];
            for (int k = 0; k < Panels.Count; k++) Panels[k].Cam.rect = rects[k + 1];
        }

        public Rect ViewRect(int k) => k == 0 ? cam.rect : Panels[k - 1].Cam.rect;

        /// Wpis do porownania: symulacja tego dnia (najpierw odtworzenie operatora), inaczej dzien innego typu.
        int PickEntryB()
        {
            if (!Data.IsSim)
            {
                var sims = Data.SimsOfDate(Data.Day.date);
                if (sims.Count > 0)
                {
                    int best = sims[0];
                    foreach (var i in sims) if (Data.Index.sims[i].scenario == "operator") { best = i; break; }
                    return Data.Index.days.Length + best;
                }
            }
            var days = Data.Index.days;
            int cur = Data.DayIndex >= 0 ? Data.DayIndex : 0;
            bool workA = days[cur].dayType == "workday";
            for (int i = days.Length - 1; i >= 0; i--)
                if (i != cur && days[i].coverage >= 0.95f && (days[i].dayType == "workday") != workA) return i;
            return (cur + 1) % days.Length;
        }

        public void ChangeDayB(int delta)
        {
            if (Mode != CompareMode.Pair) return;
            int n = Data.EntryCount;
            LoadPanel(Panels[0], ((Panels[0].Data.EntryIndex + delta) % n + n) % n);
        }

        void UpdateCompare()
        {
            float hour = Data.LocalHour(t);
            foreach (var p in Panels)
            {
                // ta sama godzina lokalna we wszystkich panelach (dzien zmiany czasu ma 25 h)
                p.Time = p.Data.TimeOfLocalHour(hour);
                p.Stations.Mode = Stations.Mode;
                p.Stations.UpdateAt(p.Time, Env.Night01);
                p.Bikes.showTrails = Bikes.showTrails;
                p.Bikes.showLoose = Bikes.showLoose;
                p.Bikes.UpdateAt(p.Time, Playing ? Speed : 1f, Playing);
                p.Trucks.gameObject.SetActive(Trucks.gameObject.activeSelf);
                p.Trucks.UpdateAt(p.Time);
                p.Agents.showPeople = Agents.showPeople;
                p.Agents.showDispatch = Agents.showDispatch;
                p.Agents.UpdateAt(p.Time, Env.Night01);
                p.Cascades.gameObject.SetActive(Cascades.gameObject.activeSelf);
                p.Cascades.UpdateAt(p.Time);
                p.Pressure.gameObject.SetActive(Pressure.gameObject.activeSelf);
                p.Pressure.UpdateAt(p.Time);
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
            if (Mode == CompareMode.Strategies) ExitCompare();
            int n = Data.Index.days.Length;
            int cur = Data.DayIndex >= 0 ? Data.DayIndex : Data.DefaultDay();
            float hour = Data.LocalHour(t);
            LoadDay(((cur + delta) % n + n) % n, 0);
            t = Data.TimeOfLocalHour(hour);
            if (Mode == CompareMode.Pair) LoadPanel(Panels[0], PickEntryB());
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
                case "Efekty": return Post != null && Post.Active;
                case "Agenci": return Agents.showPeople;
                case "Fale pustek": return Cascades.gameObject.activeSelf;
                case "Ciśnienie": return Pressure.gameObject.activeSelf;
                case "Dyspozytor": return Agents.showDispatch;
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
                case "Agenci": Agents.showPeople = on; break;
                case "Fale pustek": Cascades.gameObject.SetActive(on); break;
                case "Ciśnienie": Pressure.gameObject.SetActive(on); if (on) Pressure.OnDayLoaded(); break;
                case "Dyspozytor": Agents.showDispatch = on; break;
                case "Efekty":
                    // bloom, SSAO i odbicia w wodzie - wylaczenie przyspiesza dzialanie na slabszym komputerze
                    if (Post == null) break;
                    Post.SetEnabled(on);
                    if (Reflection != null) Reflection.enabled = on;
                    cam.GetComponent<UnityEngine.Rendering.Universal.UniversalAdditionalCameraData>().renderPostProcessing = on;
                    break;
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
        /// Kadr: ustawia godzine (z rozbiegiem, zeby rowery mialy slady), czeka i zapisuje zrzut.
        IEnumerator Shot(string dir, string name, float hour, float run = 1.5f)
        {
            t = Mathf.Clamp(Data.TimeOfLocalHour(hour) - 480f, 0, Data.Day.lengthSec - 1);
            Speed = 320f; Playing = true;
            yield return new WaitForSecondsRealtime(run);
            Playing = false;
            yield return new WaitForSecondsRealtime(0.3f);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, name + ".png"));
            Debug.Log($"Veturilo: kadr {name} - {Data.SourceLabel}, fale {Cascades.Active} (linie {Cascades.DrawnLines}, pierscienie {Cascades.DrawnRings}), " +
                      $"agenci czeka {Agents.Waiting} idzie {Agents.Walking} odchodzi {Agents.Leaving} zadania {Agents.ActiveTasks} (linie {Agents.DrawnLines}, poswiata {Agents.DrawnGlows})");
            yield return new WaitForSecondsRealtime(0.5f);
        }

        /// Kadry modelu: dane | model, strategie, agenci, dyspozytor, cisnienie, fale pustek, pasek zdarzen.
        IEnumerator SimShots(string dir)
        {
            int day = Data.DayIndex;
            string date = Data.SimCount > 0 ? Data.Index.sims[0].date : Data.Day.date;
            int real = Array.FindIndex(Data.Index.days, d => d.date == date);
            if (real >= 0) LoadDay(real, 0);

            // pasek zdarzen i fale pustek na danych
            View(2, instant: true);
            yield return Shot(dir, "26_pasek_zdarzen", 8.4f);
            var c = Data.Day.cascades;
            if (c?.len != null && c.len.Length > 0)
            {
                int best = 0;
                for (int k = 1; k < c.len.Length; k++) if (c.len[k] > c.len[best]) best = k;
                int a = c.start[best], n = c.len[best];
                var center = Vector3.zero;
                for (int i = 0; i < n; i++) { var s = Data.Stations[c.st[a + i]]; center += new Vector3(s.x, 0, s.z); }
                center /= n;
                Rig.Preset(center, 20f, 55f, 5200f, true);
                yield return Shot(dir, "25_fale_pustek", Data.LocalHour(c.t[a + n - 1]) - 0.1f);
            }
            SetLayer("Ciśnienie", true);
            View(3, instant: true);
            yield return Shot(dir, "24_cisnienie", 8.6f);
            SetLayer("Ciśnienie", false);

            if (Data.SimCount > 0)
            {
                // dane | model tego dnia
                View(2, instant: true);
                ToggleCompare();
                yield return Shot(dir, "20_dane_vs_model", 8.3f);
                ToggleCompare();

                // cztery strategie
                View(1, instant: true);
                ToggleStrategies();
                yield return Shot(dir, "21_strategie", 17.6f, 2f);
                if (Comparing) ExitCompare();

                // agenci z bliska: stacja z najwieksza liczba rezygnacji wokol 8:15 (model bez relokacji)
                LoadEntry(Data.Index.days.Length + 0, 0);
                var ag = Data.Day.agents;
                if (ag?.lostT != null && ag.lostT.Length > 0)
                {
                    float tt = Data.TimeOfLocalHour(8.25f);
                    var count = new Dictionary<int, int>();
                    for (int i = 0; i < ag.lostT.Length; i++)
                        if (Mathf.Abs(ag.lostT[i] - tt) < 1800) count[ag.lostSt[i]] = count.TryGetValue(ag.lostSt[i], out var v) ? v + 1 : 1;
                    int st = -1, bestN = 0;
                    foreach (var kv in count) if (kv.Value > bestN) { bestN = kv.Value; st = kv.Key; }
                    if (st >= 0)
                    {
                        var s = Data.Stations[st];
                        Rig.Preset(new Vector3(s.x, 0, s.z), 30f, 38f, 650f, true);
                        yield return Shot(dir, "22_agenci_blisko", 8.25f, 0.6f);
                    }
                }
                // dyspozytor: przebieg z najwieksza liczba zadan
                int disp = 0, most = -1;
                for (int i = 0; i < Data.SimCount; i++)
                {
                    LoadEntry(Data.Index.days.Length + i, 0);
                    int nTasks = Data.Day.agents?.taskT0?.Length ?? 0;
                    if (nTasks > most) { most = nTasks; disp = i; }
                }
                LoadEntry(Data.Index.days.Length + disp, 0);
                View(2, instant: true);
                yield return Shot(dir, "23_dyspozytor", 9.2f);
            }
            if (day >= 0) LoadDay(day, 0);
        }

        IEnumerator ShotSeries(string dir)
        {
            Directory.CreateDirectory(dir);
            if (Arg("-vtShotsSet") == "sim")
            {
                yield return null;
                yield return SimShots(dir);
                Application.Quit();
                yield break;
            }
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

            // ujecie na horyzont w poludnie (mgla, niebo, cienie chmur)
            t = Data.TimeOfLocalHour(12f);
            Rig.Preset(new Vector3(0, 0, -2000), 10f, 6f, 4000f, true);
            yield return new WaitForSecondsRealtime(0.6f);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "16_horyzont.png"));
            yield return new WaitForSecondsRealtime(0.5f);

            // Wisla w dzien (odbicia, cienie chmur) i deszczowy wieczor 25.10 (mokre ulice)
            View(5, instant: true);
            t = Data.TimeOfLocalHour(11.5f) - 300f;
            Speed = 300f; Playing = true;
            yield return new WaitForSecondsRealtime(1.2f);
            Playing = false;
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(dir, "14_wisla_dzien.png"));
            yield return new WaitForSecondsRealtime(0.5f);
            int home = Data.DayIndex;
            int rainy = Array.FindIndex(Data.Index.days, d => d.date == "2026-10-25");
            if (rainy >= 0)
            {
                LoadDay(rainy, 0);
                View(4, instant: true);
                t = Data.TimeOfLocalHour(19.0f) - 300f;
                Playing = true;
                yield return new WaitForSecondsRealtime(1.5f);
                Playing = false;
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(Path.Combine(dir, "15_deszcz_mokre_ulice.png"));
                yield return new WaitForSecondsRealtime(0.5f);
                LoadDay(home, 0);
            }

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

            yield return SimShots(dir);

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
