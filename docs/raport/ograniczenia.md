# Ograniczenia (materiał do rozdziału 11)

Lista zbierana na bieżąco. Każdy dopisuje ograniczenie, gdy je zauważy, z krótkim „co to zmienia”.

| Ograniczenie | Co to zmienia | Kto dopisał |
|---|---|---|
| Dane tylko z jesieni: sezon Veturilo kończy się 30.11, od 1.12 do 1.03 system jest wyłączony. Brak grudnia, przerwy świątecznej i mrozów. | Wyniki pogodowe (H1) tylko dla 1–14 °C; brak scenariuszy zimowych z danych. | Osoba 1 |
| Ostatnie dni sezonu mogą być „zwijaniem systemu” (mniej stacji, zwożenie rowerów). | Dni oznaczone w `daily_check.wind_down` wykluczamy z kalibracji i z `operator_shifts`. | Osoba 1 |
| Rozdzielczość 5 min: czas przejazdu i chwila wypożyczenia są znane z dokładnością ±5 min (czas zawyżony średnio o ok. 5 min). | Próg 20 min (A) badamy krokami 5 min; metryki emergencji liczymy z siatki 5 min także dla modelu. | Osoba 1 |
| Relokacje widoczne tylko przy ≥ 4 rowerach przewiezionych naraz; liczby ciężarówek operatora nie znamy. | `operator_shifts` mówi, *kiedy* operator pracuje, a nie *ile* ma aut; mniejsze przewozy giną w ruchu klientów. | Osoba 1 |
| Brak tożsamości klientów. | Liczba stałych bywalców to dolne oszacowanie z regularności tras (`commute_pairs.regular_days_*`). | Osoba 1 |
| Utraceni klienci są nieobserwowalni w danych (nikt nie notuje, że ktoś odszedł od pustej stacji). | Utracony popyt w danych to szacunek (popyt × czas pustki); dokładny tylko w modelu. Obserwacja w terenie (Osoba 2) przy 10 stacjach z `top10_puste_rano.csv`. | Osoba 1 |
| Feed nie podaje `last_reported`, a pytamy co 5 min. | Opóźnienia aplikacji nie da się zmierzyć z danych – pomiar ręczny (`tools/app_latency.py`) albo parametr scenariusza 0 / 5 / 10 min. | Osoba 1 |
| Granice dzielnic z OSM (admin_level 9); Bemowo jako reszta miasta po odjęciu pozostałych 17 dzielnic. | Powierzchnie zgodne z oficjalnymi (Bemowo 24,9 km²); błąd na styku dzielnic do kilkudziesięciu metrów. | Osoba 1 |
