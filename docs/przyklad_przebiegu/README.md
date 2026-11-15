# Przykładowy przebieg symulacji (format z agentami)

Wzór plików, które zapisuje silnik agentowy: pierwsze 12 h przebiegu `operator_2 / seed_1000` (5.11) z dopisanymi **nowymi** zdarzeniami agentów (`user_wait_start/end`, `user_walk`, `user_leave`, `signal_on/off`, `task_announced`, `bid`, `task_awarded`, pola `user_id`, `user_type`, `has_app`, `n_bikes`) i kolumną `pressure` w `station_timeseries`. Wartości nowych zdarzeń są umowne (losowane) – liczy się format.

Opis kolumn i typów zdarzeń: [docs/kontrakty.md](../kontrakty.md), sekcja 2. Odtworzenie:

```bash
python tools/przyklad_przebiegu.py results/sim/operator_2/seed_1000 --out docs/przyklad_przebiegu
```

Sprawdzenie formatu: `tests/test_export_sim.py` (zdarzenia agentów, braki `pd.NA`, `pressure` i sygnały).
