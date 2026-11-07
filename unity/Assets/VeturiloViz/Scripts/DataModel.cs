// Klasy odpowiadajace plikom JSON z python -m src.viz.export.
// Nazwy pol musza byc identyczne jak w JSON (JsonUtility).
using System;

namespace Veturilo.Viz
{
    [Serializable] public class IndexFile
    {
        public string source;
        public string generated;
        public float originLat;
        public float originLon;
        public int slotSec;
        public DayEntry[] days;
        public SimEntry[] sims;   // przebiegi symulacji DES (python -m src.viz.export_sim)
    }

    [Serializable] public class SimEntry
    {
        public string key;
        public string date;
        public string label;      // np. "strategia progowa, 2 ciężar."
        public string file;
        public string scenario;
        public int trucks;
        public int seed;
        public int trips;
        public float lost;
        public float coverage;
        public string dayType;
    }

    [Serializable] public class DayEntry
    {
        public string date;
        public string label;
        public string file;
        public int trips;
        public float coverage;
        public string dayType;
        public float lost;
    }

    [Serializable] public class StationsFile { public StationInfo[] stations; }

    [Serializable] public class StationInfo
    {
        public string id;
        public string name;
        public float x;
        public float z;
        public int cap;
        public float shareEmpty;
        public float shareOverfull;
        public float meanBikes;
        public int nRestaurants;
        public int nBars;
        public int nCafes;
        public int nOffices;
        public int nUniversities;
        public int nSchools;
        public int distMetro;
        public int distCenter;
        public int population;
        public int transitDepartures;
        public int cyclewayM;
        public float elevation;
    }

    [Serializable] public class CityFile
    {
        public Building[] buildings;
        public Polyline[] cycleways;
        public Poi[] pois;
    }

    [Serializable] public class Building { public float h; public int[] p; }
    [Serializable] public class Polyline { public int[] p; }
    [Serializable] public class Poi { public string c; public string n; public float x; public float z; }

    [Serializable] public class RoutesFile { public Polyline[] routes; }

    // ------------------------------------------------------------------ podklad mapy

    [Serializable] public class BasemapFile
    {
        public Polyline[] boundary;
        public MeshData water;
        public MeshData green;
        public MeshData forest;
        public Road[] roads;      // k: 0 autostrada/ekspresowa, 1 glowna, 2 zbiorcza, 3 lokalna; b: 1 = most
        public Polyline[] rail;
        public Road[] metro;      // k: 1 = M1, 2 = M2
        public int[] trees;       // [x, z, ...]
        public PopHex[] population;
    }

    [Serializable] public class MeshData { public int[] v; public int[] t; }
    [Serializable] public class Road { public int k; public int b; public int[] p; }

    [Serializable] public class BuildingsFile { public int tile; public BuildingTile[] tiles; }
    /// Kafelek budynkow: h - wysokosci, n - liczba wierzcholkow kazdego obrysu, p - wspolrzedne wszystkich obrysow.
    [Serializable] public class BuildingTile { public float[] h; public int[] n; public int[] p; }
    [Serializable] public class PopHex { public int x; public int z; public int pop; }

    // ------------------------------------------------------------------ dzien

    [Serializable] public class DayFile
    {
        public string date;
        public string label;
        public string dayType;
        public int uniClasses;
        public string[] events;
        public long startEpoch;
        public int tzOffsetSec;
        public int lengthSec;
        public int slotSec;
        public float coverage;
        public string source;            // "observed" albo "sim"
        public string scenario;          // symulacja: none / operator / threshold / ...
        public string scenarioLabel;
        public int nTrucks;
        public int seed;
        public SimKpi simKpi;
        public string routesFile;        // symulacja: wlasne trasy (pary stacji spoza danych)
        public string truckRoutesFile;
        public Agents agents;
        public Cascades cascades;
        public StationState[] states;
        public Kpi kpi;
        public Trips trips;
        public Trucks trucks;
        public Hours hours;
        public EventInfo[] eventList;
        public Traffic traffic;
        public Incidents incidents;
        public LooseBikes loose;
        public LostDemand lost;
    }

    /// Szacowany utracony popyt: cum[stacja * steps + krok] - narastajaco od polnocy (co stepSec),
    /// rate[stacja * 24 + godzina] - popyt stacji [wypozyczenia / h, gdy sa rowery].
    /// exact = 1: dokladne zdarzenia z symulacji (lost_demand), 0: szacunek z danych.
    [Serializable] public class LostDemand { public int stepSec; public int steps; public float[] cum; public float[] rate; public float total; public int exact; }

    /// b - rowery, e - e-rowery (-1 = brak danych), p - "cisnienie" stacji x100 (-100 brak rowerow .. 100 nadmiar; opcjonalne).
    [Serializable] public class StationState { public int[] b; public int[] e; public int[] p; }

    [Serializable] public class SimKpi
    {
        public float requests;
        public float rentals;
        public float lost_demand;
        public float lost_share;
        public float truck_km;
        public float relocated_bikes;
        public float empty_station_share;
    }

    /// Agenci z symulacji (czasy w sekundach od lokalnej polnocy, stacje = indeksy w stations.json).
    /// Typ klienta: 0 inny, 1 dojezdzajacy, 2 student, 3 rekreacyjny, 4 e-rowerzysta.
    [Serializable] public class Agents
    {
        public int[] lostT, lostSt, lostType;                        // rezygnacja przy pustej stacji
        public int[] walkT, walkEnd, walkFrom, walkTo, walkType;     // przejscie do sasiedniej stacji
        public int[] waitT, waitEnd, waitSt, waitType;               // czekanie przy stacji (nowe zdarzenia)
        public int[] taskT0, taskT1, taskTruck, taskPick, taskDrop, taskN;   // zadania dyspozytora
        public int[] sigT, sigSt, sigOn;                             // sygnal stacji "potrzebuje rowerow"
    }

    /// Fale pustek: fala k = stacje st[start[k] .. start[k] + len[k]) pustoszejace w chwilach t[...].
    [Serializable] public class Cascades { public int[] start; public int[] len; public int[] st; public int[] t; }

    [Serializable] public class Kpi
    {
        public int[] empty;
        public int[] overfull;
        public int[] atStations;
        public int[] inUse;
        public int[] awayLong;
        public int[] looseWarsaw;
        public int fleetTarget;
        public int[] known;
        public int[] tripsPerHour;
    }

    [Serializable] public class Trips
    {
        public int[] dep;
        public int[] arr;
        public int[] route;
        public int[] ebike;
        public int[] bike;
        public float[] km;
        public int[] fromSt;
        public int[] toSt;
        public int[] fx;
        public int[] fz;
        public int[] tx;
        public int[] tz;
        public int[] kind;   // dane: 1 = trasa dojazdowa; symulacja: typ klienta (jak w Agents)
    }

    [Serializable] public class Trucks
    {
        public int[] dep;
        public int[] arr;
        public int[] route;
        public int[] n;
        public int[] fromSt;
        public int[] toSt;
        public int[] truck;  // symulacja: numer ciezarowki (dane: brak)
    }

    [Serializable] public class Hours
    {
        public int[] localHour;
        public float[] temp;
        public float[] apparentTemp;
        public float[] precip;
        public float[] cloud;
        public float[] wind;
        public float[] humidity;
        public float[] sunElevation;
        public int[] weatherCode;
        public float[] congestion;
        public float[] aqi;
    }

    [Serializable] public class EventInfo
    {
        public string name;
        public string venue;
        public string category;
        public float x;
        public float z;
        public int start;   // sekundy od lokalnej polnocy
        public int end;
        public int large;
    }

    [Serializable] public class Traffic { public int stepSec; public Corridor[] corridors; }

    [Serializable] public class Corridor
    {
        public string name;
        public string label;
        public float x;
        public float z;
        public float[] cong;   // co stepSec; -1 = brak pomiaru
    }

    [Serializable] public class Incidents
    {
        public int stepSec;
        public int[] step;
        public int[] x;
        public int[] z;
        public int[] cat;   // 1 wypadek, 6 korek, 7 zamkniety pas, 8 zamknieta droga, 9 roboty
        public int[] mag;
    }

    [Serializable] public class LooseBikes { public int[] slot; public int[] x; public int[] z; public int[] e; }
}
