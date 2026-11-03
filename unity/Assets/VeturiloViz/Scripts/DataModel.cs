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
    }

    [Serializable] public class DayEntry
    {
        public string date;
        public string label;
        public string file;
        public int trips;
        public float coverage;
        public string dayType;
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
        public Road[] roads;      // k: 0 autostrada/ekspresowa, 1 glowna, 2 zbiorcza, 3 lokalna
        public Polyline[] rail;
        public PopHex[] population;
    }

    [Serializable] public class MeshData { public int[] v; public int[] t; }
    [Serializable] public class Road { public int k; public int[] p; }
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
        public StationState[] states;
        public Kpi kpi;
        public Trips trips;
        public Trucks trucks;
        public Hours hours;
        public EventInfo[] eventList;
        public Traffic traffic;
        public Incidents incidents;
        public LooseBikes loose;
    }

    [Serializable] public class StationState { public int[] b; public int[] e; }

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
        public int[] fromSt;
        public int[] toSt;
        public int[] fx;
        public int[] fz;
        public int[] tx;
        public int[] tz;
    }

    [Serializable] public class Trucks
    {
        public int[] dep;
        public int[] arr;
        public int[] route;
        public int[] n;
        public int[] fromSt;
        public int[] toSt;
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
