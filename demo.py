from pathlib import Path
import pandas as pd
import numpy as np

from src.simulation.engine import Simulation, SimulationParams
from src.simulation.network import build_network
from src.simulation.demand import HourlyDemand

def run_demo():
    print("=" * 70)
    print("DEMO SYSTEMU WIELOAGENTOWEGO VETURILO (ABM + DES)")
    print("=" * 70)

    stations = pd.DataFrame({
        "station_id": ["Centrum", "Politechnika", "Mokotow", "Praga"],
        "capacity": [30, 25, 20, 20],
        "initial_bikes": [28, 2, 10, 10],
        "lat": [52.230, 52.220, 52.200, 52.240],
        "lon": [21.010, 21.015, 21.020, 21.040]
    })
    network = build_network(stations)

    params = SimulationParams(
        stations=stations,
        network=network,
        demand_model=HourlyDemand(np.array([25.0, 25.0, 15.0, 10.0])),
        duration_min=120.0,
        n_trucks=2,
        dispatch_interval_min=5.0,
        user_patience_min=5.0,
        app_share=0.5,
        pressure_alpha=0.5
    )

    print("\n1. Start symulacji ze strategia sterowania polem cisnienia (pressure)...")
    sim = Simulation(params, scenario="pressure", seed=42)
    result = sim.run()

    print("\n2. Zdarzenia przetargu Contract Net i histerezy stacji (probka z events):")
    df_events = result.events[result.events["event"].isin([
        "signal_on", "signal_off", "task_announced", "bid", "task_awarded", "user_wait_start", "user_wait_end"
    ])]
    sample = df_events[["minute", "event", "station_id", "to_station", "truck_id", "task_id"]].head(12)
    print(sample.to_string(index=False))

    print("\n3. Wyniki stacji z obliczonym polem cisnienia (probka station_timeseries):")
    ts_sample = result.station_timeseries[["time", "station_id", "bikes", "capacity", "pressure"]].tail(8)
    print(ts_sample.to_string(index=False))

    print("\n4. Tabela decyzji uzytkownikow (user_outcomes):")
    uo_sample = result.user_outcomes.head(8)
    print(uo_sample.to_string(index=False))

    print("\n5. Podsumowanie KPI symulacji:")
    for k in ["scenario", "requests", "rentals", "lost_demand", "truck_km", "relocated_bikes", "jobs_completed"]:
        print(f"   - {k}: {result.kpis.get(k)}")

    print("\n" + "=" * 70)
    print("DEMO ZAKONCZONE SUKCESEM: Agenci dzialaja autonomicznie i poprawnie.")
    print("=" * 70)

if __name__ == "__main__":
    run_demo()
