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
        public int nOffices;
        public int nUniversities;
        public int distMetro;
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
    }

    [Serializable] public class StationState { public int[] b; public int[] e; }

    [Serializable] public class Kpi
    {
        public int[] empty;
        public int[] overfull;
        public int[] atStations;
        public int[] inUse;
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
        public float[] precip;
        public float[] cloud;
        public float[] wind;
        public float[] sunElevation;
        public int[] weatherCode;
        public float[] congestion;
        public float[] aqi;
    }
}
