// Pokaz z komentarzem (klawisz T): ok. 2 min przelotu przez caly dzien - kamera, widoki i napisy
// zmieniaja sie o zadanych godzinach. Liczby w napisach pochodza z wczytanych danych.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace Veturilo.Viz
{
    public class Tour
    {
        readonly VeturiloApp app;
        readonly List<(float hour, Action act, Func<string> text)> steps = new List<(float, Action, Func<string>)>();
        int next;
        public bool Running { get; private set; }

        const float Speed = 480f;        // 1 s = 8 min
        const float CaptionSec = 10f;

        public Tour(VeturiloApp app)
        {
            this.app = app;
            var d = app.Data;
            Add(5.5f, () => { Fill(); app.View(1); Slow(0.6f); },
                () => $"To nie animacja, tylko prawdziwy dzień: {d.Day.label}. Każdy świecący punkt to jeden przejazd " +
                      $"odtworzony z numerów rowerów – {d.Day.trips.dep.Length:N0} przejazdów tego dnia.".Replace(",", " "));
            Add(7.0f, () => { Fly(new Vector3(-800, 0, -600), 28f, 40f, 9500f); },
                () => "Poranny szczyt: rowery jadą z osiedli do centrum – do pracy, szkół i na uczelnie.");
            Add(8.0f, () => { app.SetMode(ViewMode.Balance); app.SetLayer("Łuki OD", true); Fly(new Vector3(0, 0, -800), 10f, 62f, 13500f); },
                () => "Bilans ostatniej godziny: czerwone stacje tracą rowery, niebieskie zyskują. Łuki pokazują najczęstsze trasy.");
            Add(9.4f, () => { Fill(); app.SetLayer("Łuki OD", false); Fly(new Vector3(-300, 0, 0), 35f, 42f, 3800f); },
                () => "Skutek: centrum jest przepełnione (fiolet), a na obrzeżach stacje pustoszeją – pulsują na czerwono.");
            Add(11.0f, () => { Fly(new Vector3(200, 0, -400), 300f, 48f, 6500f); },
                () => "Pomarańczowe ciężarówki to relokacje operatora (+ liczba przewożonych rowerów). " +
                      "To strategia bazowa, z którą porównamy strategie w symulacji DES.");
            Add(13.0f, () => { app.SetMode(ViewMode.Problem); Fly(new Vector3(0, 0, -900), 15f, 48f, 15000f); },
                () => $"Hipoteza H2: puste stacje są skoncentrowane. 10% stacji odpowiada za {d.Top10Share:P0} czasu pustek, " +
                      $"a {d.NeverEmptyShare:P0} stacji nie było pustych ani razu.");
            Add(14.8f, () => { Fill(); app.SetLayer("Korki", true); Fly(new Vector3(0, 0, -900), 340f, 38f, 11000f); },
                () => "Kontekst z danych: pogoda, korki TomTom na arteriach (słupki), utrudnienia i wydarzenia – zmienne modelu popytu.");
            Add(16.2f, () => { app.Rig.cinematic = true; },
                () => "Popołudniowy szczyt – największy ruch dnia.");
            Add(17.6f, () => { app.View(4); Slow(0.8f); },
                () => "Po zmroku zapalają się okna i latarnie, a ruch rowerów słabnie – pora dnia to jedna ze zmiennych modelu.");
            Add(20.3f, () => { app.View(1); },
                () => "Ta sama scena przyjmie wynik symulacji DES – pokażemy model obok rzeczywistości.");
            Add(21.2f, () => Stop(), null);
        }

        void Add(float hour, Action act, Func<string> text) => steps.Add((hour, act, text));

        void Fill() => app.SetMode(ViewMode.Fill);
        void Slow(float smoothing) => app.Rig.Smoothing = smoothing;

        void Fly(Vector3 target, float yaw, float pitch, float dist)
        {
            app.Rig.Preset(target, yaw, pitch, dist);
            app.Rig.Smoothing = 0.7f;   // wolny przelot zamiast skoku
        }

        public void Start()
        {
            Running = true;
            next = 0;
            app.Stations.Selected = null;
            app.SetLayer("Łuki OD", false);
            app.SetLayer("Ślady", true);
            app.SeekLocalHour(steps[0].hour - 0.05f);
            app.SetSpeed(Speed);
        }

        public void Stop()
        {
            Running = false;
            app.Rig.Smoothing = 8f;
            app.Rig.cinematic = false;
        }

        public void Update(float t)
        {
            if (!Running) return;
            float hour = app.Data.LocalHour(t);
            while (next < steps.Count && hour >= steps[next].hour)
            {
                var s = steps[next++];
                s.act();
                if (s.text != null) app.Hud.ShowCaption(s.text(), CaptionSec);
            }
        }
    }
}
