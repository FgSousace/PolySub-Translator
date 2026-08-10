## Poprawki w wersji 0.5.2

- naprawiono automatyczną instalację oficjalnego PyTorch ROCm 7.14 na Windows: instalator nie
  blokuje już wymaganego pakietu `rocm-7.14.0.tar.gz` przez błędne `--only-binary`;
- przerwane środowisko AMD z wersji 0.5.1 jest automatycznie dokańczane przy następnym
  uruchomieniu lub po kliknięciu **Odśwież listę sprzętu** — bez ręcznego instalowania Pythona;
- skaner modeli przechwytuje `WinError 448` i inne błędy niedostępnych punktów instalacji,
  dowiązań oraz uszkodzonych snapshotów Hugging Face zamiast zamykać całe GUI;
- wadliwy snapshot jest pomijany, a program nadal wyszukuje inną kompletną kopię modelu;
  jeżeli jej nie ma, model otrzymuje czytelny stan **Cache niedostępny** i można go usunąć
  oraz pobrać ponownie z poziomu menedżera;
- nowe pobrania modeli używają na Windows oficjalnego trybu Hugging Face bez symlinków,
  aby błąd niezaufanego punktu nie powstawał ponownie;
- diagnostyka cache modeli jest zapisywana w
  `%LOCALAPPDATA%\PolySub Translator\model-cache-diagnostics.log`;
- zachowano izolowanie właściwej karty Radeon od iGPU przez `HIP_VISIBLE_DEVICES` oraz
  rzeczywisty test mnożenia macierzy przed oznaczeniem GPU jako gotowego;
- gotowe pliki mają wersjonowane nazwy `PolySub-Translator-Setup-0.5.2.exe` i
  `PolySub-Translator-Installer-0.5.2.zip`.

Wersje 0.5.1, 0.5.0 i wszystkie wcześniejsze pozostają osobno w historii GitHub Releases.

## Wcześniej poprawione w wersji 0.5.1

- naprawiono akcelerację RX 9070 XT w komputerach z procesorem Ryzen posiadającym iGPU;
- automat sprawdza każdy indeks HIP osobno, rozpoznaje właściwą kartę dyskretną i pomija
  niezgodne zintegrowane Radeon Graphics;
- worker ustawia natywne dla Windows `HIP_VISIBLE_DEVICES`, dzięki czemu wybrana karta
  RX 9070 XT jest izolowana i widoczna dla modelu jako działające `cuda:0`;
- test wykorzystuje również bezpośrednią liczbę urządzeń HIP, aby ominąć błędne wskazanie
  zewnętrznego AMD SMI;
- wszystkie etapy automatycznego przygotowania AMD trafiają do widocznego dziennika oraz pliku
  `%LOCALAPPDATA%\PolySub Translator\amd-runtime-diagnostics.log`; błąd nie jest już cichy;
- pliki pobierane z GitHub Releases zawierają numer wersji, na przykład
  `PolySub-Translator-Setup-0.5.1.exe` i `PolySub-Translator-Installer-0.5.1.zip`;
- aktualizator preferuje nową nazwę z numerem, zachowując zgodność ze starszymi wydaniami.

Wersje 0.5.0, 0.4.9, 0.4.8, 0.4.7, 0.4.6, 0.4.5 i 0.4.4 pozostają osobno
w historii GitHub Releases.

## Wcześniej dodane w wersji 0.5.0

- obsługa AMD na Windows uruchamia się teraz **automatycznie** po wykryciu zgodnego Radeona;
  usunięto osobny przycisk konfiguracji i pytanie o ręczne rozpoczęcie pobierania;
- środowisko AMD zostało zaktualizowane z ROCm 7.2.1 do oficjalnego **ROCm 7.14.0** oraz
  PyTorch 2.12.0 z repozytorium AMD;
- RX 9070 XT jest rozpoznawany jako architektura **gfx1201** i otrzymuje mniejszy, właściwy
  pakiet zamiast uniwersalnego zestawu dla wszystkich kart;
- program pobiera własną, odizolowaną dystrybucję Python 3.12 z python.org, więc użytkownik
  nie musi instalować Pythona ani zmieniać systemowego środowiska;
- automat rozróżnia oficjalne cele AMD dla RX 9000, RX 7000, wybranych RDNA2, Radeon PRO
  i Radeonów w układach Ryzen; przy kilku różnych kartach dobiera pakiet wieloarchitekturowy;
- karta zostaje oznaczona jako gotowa dopiero po rzeczywistym mnożeniu macierzy na GPU;
  brak pakietu, internetu, zgodnego Windows lub sterownika powoduje jawny powrót na CPU;
- przerwane przygotowanie środowiska AMD jest naprawiane automatycznie przy następnym
  uruchomieniu albo po użyciu przycisku **Odśwież listę sprzętu**;
- wydanie zawiera `Setup.exe` i ZIP z instalatorem. Nowa paczka portable nie jest tworzona.

## Wcześniej dodane w wersji 0.4.9

- główny przycisk prowadzi najpierw do **Wyszukaj napisy w filmie lub wybierz plik**, a po
  prawidłowym wczytaniu zmienia się w **Rozpocznij tłumaczenie**;
- okno wyboru ma wspólny filtr wszystkich obsługiwanych SRT i filmów, osobne filtry formatów
  oraz **Wszystkie pliki (*.*)**; aplikacja opisuje typ pliku i odrzuca nieobsługiwane dane;
- tryb automatyczny i tryb weryfikacji są wymaganymi, wzajemnie wykluczającymi się checkboxami;
- główna lista modeli pokazuje wyłącznie dodatki faktycznie pobrane, kompletne i gotowe;
- przycisk **Anuluj tłumaczenie** kończy pracę bez czyszczenia punktu wznowienia, dlatego
  ukończone partie nie przepadają;
- NVIDIA została zaktualizowana do PyTorch 2.11 z CUDA 12.8 i cuDNN 9 dla GTX 10 oraz
  RTX 20/30/40/50 z aktualnym sterownikiem;
- dodano konfigurator odizolowanego AMD ROCm 7.2.1 dla Windows 11: pobiera oficjalne paczki AMD,
  sprawdza prawdziwy backend i uruchamia tłumaczenie w osobnym procesie, aby nie kolidowało
  z bibliotekami NVIDIA;
- RX 9070 XT jest na oficjalnej liście AMD i po przejściu testu pojawia się jako gotowy backend
  ROCm; niewspierana albo nieskonfigurowana karta pozostaje jawnie na CPU;
- dodano stałe oznaczenie **PolySub Translator™**, autora **fgSousace**, metadane EXE, ekran
  „O programie”, `NOTICE.txt` i pełną instrukcję obsługi;
- od v0.4.9 oryginalny kod aplikacji jest udostępniany na warunkach PolyForm Noncommercial
  License 1.0.0: użytek osobisty i inny niekomercyjny jest dozwolony, a komercyjny wymaga
  osobnej zgody autora;
- instalator publikuje `Setup.exe` i ZIP z instalatorem; nowa paczka portable nie jest tworzona.

Wersje 0.4.8, 0.4.7, 0.4.6, 0.4.5 i 0.4.4 pozostają osobno w historii GitHub Releases.

## Wcześniej dodane w wersji 0.4.8

- całkowicie odświeżony, domyślny interfejs **Nowoczesny** ma stały panel boczny i pięć skrótów:
  Start, Tłumaczenie, Modele AI, Film i sprzęt oraz Ustawienia;
- poprzedni układ pozostaje dostępny jako **Klasyczny 0.4.7** i można do niego wrócić w każdej
  chwili;
- przełączanie układu zachowuje wybrany plik, języki, silnik, model, profil napisów i kontekst;
- dodano 10 motywów: Automatyczny — system, OLED Black, Midnight Blue, Graphite Pro, Cyber Neon,
  Aurora Violet, Emerald Matrix, Crimson Studio, Arctic Light i Warm Sand;
- domyślny Midnight Blue zapewnia czytelny, nowoczesny ciemny wygląd, a OLED Black używa
  prawdziwej czerni `#000000`;
- szybki wybór motywu znajduje się na dole panelu bocznego, a pełne ustawienia wyglądu mają opis
  każdego wariantu i przycisk przywrócenia ustawień domyślnych;
- wybrany interfejs i motyw są trwale zapisywane w profilu użytkownika;
- motywy obejmują główne okno, kontrolki, pola tekstowe, menedżer modeli i okno weryfikacji;
- test gotowego EXE przełącza nowy i klasyczny układ, sprawdza wszystkie najważniejsze kontrolki,
  motyw OLED oraz zachowanie danych formularza;
- wydanie zawiera `Setup.exe` i ZIP z instalatorem. Nowa paczka portable nie jest tworzona.

Wersje 0.4.7, 0.4.6, 0.4.5 i 0.4.4 pozostają osobno w historii GitHub Releases.

## Wcześniej dodane w wersji 0.4.7

- nowa sekcja **Czas wyświetlania napisów** udostępnia pięć czytelnych kafelków: Zalecane,
  Krótsze, Dłuższe, Oryginalne oraz Własne; zaznaczony profil i jego parametry są wyraźnie
  wyróżnione, a pola liczbowe pojawiają się dopiero dla trybu Własne;
- domyślny profil Zalecane oblicza potrzebny czas z długości przetłumaczonego tekstu: minimum
  1,5 sekundy i maksymalnie 17 znaków na sekundę, o ile pozwala na to przerwa w dialogu;
- program nie zmienia początków wypowiedzi ani nie łączy różnych postaci; stary napis zawsze kończy
  się przed wejściem następnego, a istniejące nakładanie jest automatycznie przycinane;
- po tłumaczeniu podsumowanie pokazuje liczbę dopasowanych napisów i wpisów, których nie dało się
  wydłużyć z powodu natychmiastowej następnej wypowiedzi;
- CLI otrzymało `--subtitle-timing`, `--minimum-subtitle-seconds` i `--subtitle-cps`;
- nowy **Menedżer modeli AI** pokazuje 20 opcjonalnych modeli w orientacyjnej kolejności od
  najmocniejszych do najlżejszych;
- każdy wpis pokazuje rozmiar pobierania, wymagania RAM/VRAM, zakres języków, jakość, licencję oraz
  stan pobrania;
- obsługiwane rodziny to MADLAD-400, NLLB-200, M2M100, mBART-50 i OPUS/Marian;
- modele są pobierane dopiero po potwierdzeniu z oficjalnych repozytoriów Hugging Face; przerwaną
  operację można wznowić, a każdy dodatek można osobno usunąć;
- program sprawdza zgodność wybranego modelu z parą językową i nie pozwala przypadkowo uruchomić
  np. modelu English → Polish dla innego języka;
- domyślny M2M100 418M zachowuje zgodność ze starszymi punktami wznowienia PolySub;
- instalator może po zakończeniu opcjonalnie otworzyć menedżer modeli, ale nie zawiera wielkich wag;
- interfejs terminalowy otrzymał `--list-models`, `--manage-models` i `--local-model`;
- test instalatora sprawdza kompletność dokładnie 20 modeli, mechanizm pobierania oraz wszystkie
  profile czasu i brak nachodzenia kolejnych wypowiedzi.

Ranking jakości jest orientacyjny. Przed pobraniem program pokazuje licencję; modele NLLB są
badawcze i niekomercyjne na warunkach CC-BY-NC-4.0.

Wersje 0.4.6, 0.4.5 i 0.4.4 pozostają osobno w historii GitHub Releases. Wydanie 0.4.7 zawiera
`Setup.exe` oraz ZIP z instalatorem, bez nowej paczki portable.

## Wcześniej dodane w wersji 0.4.6

- nowy przycisk **Wypal napisy na obrazie — TV** tworzy film, w którym napisy są na stałe
  częścią każdej klatki i nie trzeba włączać ich w odtwarzaczu;
- dotychczasowa szybka, przełączana ścieżka pozostaje dostępna jako osobna opcja i nadal nie
  przelicza obrazu ani dźwięku;
- wypalanie automatycznie próbuje NVIDIA NVENC, Intel Quick Sync i AMD AMF, a gdy sprzętowy koder
  nie zadziała, bezpiecznie ponawia operację przez CPU;
- pasek pokazuje rzeczywisty czas przetworzonego filmu podczas wypalania;
- ustawienie **Wykorzystanie procesora** pozwala wybrać 25%, 50%, 75% albo 100% logicznych wątków;
- lokalne M2M100 i Whisper otrzymują prawdziwą liczbę wątków, a większe partie tłumaczenia lepiej
  wykorzystują wielordzeniowe procesory bez zmiany jakości modelu;
- instalator zawiera PyTorch z CUDA 12.6 oraz cuDNN 9, dzięki czemu obsługuje również RTX 2080
  i inne zgodne karty NVIDIA ze zaktualizowanym sterownikiem;
- gotowy instalator przechodzi dodatkowe testy wykorzystania CPU, bibliotek NVIDIA oraz wypalania
  napisów przed publikacją.

Wydania 0.4.5 i 0.4.4 pozostają dostępne osobno w historii GitHub Releases i nie są usuwane.

## Wcześniej dodane w wersji 0.4.5

- dynamiczna lista pokazuje prawdziwy model procesora i wszystkie wykryte karty graficzne;
- tryb **Automatycznie** osobno wybiera najlepsze urządzenie do tłumaczenia i rozpoznawania mowy;
- można ręcznie wskazać konkretny CPU albo GPU, również w komputerze z kilkoma kartami;
- program wykrywa dostępne backendy CUDA, ROCm oraz Intel XPU zamiast zgadywać po nazwie sprzętu;
- przy braku zgodnego backendu wyświetla jasną informację i bezpiecznie przechodzi na CPU;
- błąd GPU podczas ładowania lub obliczeń powoduje automatyczne ponowienie zadania na procesorze;
- przycisk **Odśwież listę sprzętu** ponownie sprawdza urządzenia bez restartowania programu.

Wydanie 0.4.4 pozostaje dostępne osobno w historii GitHub Releases.

## Wcześniej dodane w wersji 0.4.4

- program automatycznie sprawdza w tle najnowsze wydanie po uruchomieniu;
- przycisk **Sprawdź aktualizacje** pozwala powtórzyć sprawdzenie w dowolnym momencie;
- gdy pojawi się nowsza wersja, program pokazuje numer zainstalowanej i najnowszej wersji;
- przycisk pobierania prowadzi bezpośrednio do oficjalnego instalatora z GitHub Releases;
- aktualizacje nie instalują się ani nie uruchamiają bez zgody użytkownika.

## Wcześniej dodane w wersji 0.4.3

- dwa poziome paski: liczba ukończonych etapów i postęp bieżącej czynności;
- dziennik pokazujący ładowanie modeli, wykrywanie języka, tłumaczenie, kontrolę i zapis;
- licznik czasu z komunikatem potwierdzającym, że program nadal działa;
- przewijane ustawienia oraz przyciski przypięte na dole, aby nie znikały na mniejszych ekranach;
- lepsze skalowanie DPI w Windows.

## Dwa wygodne sposoby instalacji na Windows

### Najszybciej

1. Pobierz `PolySub-Translator-Setup-0.5.2.exe`.
2. Uruchom plik, wybierz katalog i kliknij **Instaluj**.

### Instalator w ZIP-ie

1. Pobierz `PolySub-Translator-Installer-0.5.2.zip`.
2. Rozpakuj go — w środku są `PolySub-Translator-Setup-0.5.2.exe` i `README.txt`.
3. Uruchom instalator.

Po instalacji kreator pokazuje krótką instrukcję i pozwala od razu uruchomić program. Skrót
**PolySub Translator** jest dostępny na pulpicie oraz w menu Start.

Nie pobieraj plików `Source code`, jeżeli chcesz po prostu uruchomić program.

Windows SmartScreen może wyświetlić ostrzeżenie, ponieważ instalator nie ma jeszcze płatnego
certyfikatu podpisu cyfrowego. W takim przypadku wybierz **Więcej informacji → Uruchom mimo to**.

Instalator nie wymaga Pythona, Gita ani uprawnień administratora. Wydania 0.4.6–0.5.2 nie zawierają nowej
paczki portable, ponieważ dołączone biblioteki CUDA przekroczyłyby limit pojedynczego pliku GitHub
Releases. Portable z wersji 0.4.5 nadal pozostaje dostępne w historii wydań.
