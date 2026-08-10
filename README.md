# PolySub Translator™

**Autor: fgSousace • Copyright © 2026 fgSousace • użytek niekomercyjny**

**Context-aware multilingual subtitle translator with automatic language detection and
interactive review.**

PolySub tłumaczy kompletne pliki `.srt` albo sam przygotowuje napisy z filmu, zachowując numery
kwestii, początki wypowiedzi i podstawowe formatowanie. Użytkownik wybiera silnik lokalny albo DeepL API
oraz jeden z dwóch trybów: szybkie tłumaczenie automatyczne lub tłumaczenie z ręczną weryfikacją
niejasnych fragmentów.

> Status: `v0.5.3` — automatyczna akceleracja zgodnych Radeonów i NVIDIA, odporne
> skanowanie modeli, paczka bez UPX, anulowanie z bezpiecznym wznowieniem oraz tylko gotowe
> modele w GUI.

## Najważniejsze funkcje

- automatyczne wykrywanie języka całego pliku;
- dodatkowy import MP4/MKV/MOV/M4V/AVI/WebM bez usuwania obsługi SRT;
- wyciąganie pierwszej tekstowej ścieżki napisów z filmu;
- lokalne rozpoznawanie mowy przez Whisper, gdy film nie zawiera napisów;
- szybkie dołączanie gotowych napisów do filmu bez ponownego kodowania obrazu i dźwięku;
- wypalanie napisów na stałe w obrazie filmu z automatyczną akceleracją NVIDIA, Intel lub AMD;
- wybór dowolnego języka docelowego obsługiwanego przez wybrany silnik;
- katalog 20 lokalnych modeli AI z pobieraniem, usuwaniem i kontrolą zgodności języków;
- lokalne silniki MADLAD-400, NLLB-200, M2M100, mBART-50 i OPUS albo DeepL API;
- dynamiczna lista rzeczywiście wykrytych procesorów i kart NVIDIA, AMD oraz Intel;
- tryb Auto wybierający najlepszy zgodny backend z bezpiecznym powrotem na CPU;
- automatyczne pobieranie właściwego środowiska ROCm dla zgodnego Radeona bez osobnego przycisku;
- wybór limitu 25%, 50%, 75% albo 100% logicznych wątków procesora;
- dwa paski postępu: wszystkie etapy operacji oraz dokładny postęp bieżącego etapu;
- dziennik wykonywanych czynności, czas pracy, procenty, liczba słów i czas nagrania;
- przewijany interfejs z przyciskami stale widocznymi na dole również na mniejszych ekranach;
- automatyczne sprawdzanie najnowszej wersji oraz ręczny przycisk pobrania aktualizacji;
- wybór nowoczesnego albo klasycznego interfejsu oraz 10 zapamiętywanych motywów;
- pięć profili czasu napisów: Zalecane, Krótsze, Dłuższe, Oryginalne i Własne;
- zachowanie początku każdej wypowiedzi oraz automatyczne zapobieganie nachodzeniu napisów;
- zapis awaryjny i automatyczne wznowienie przerwanego zadania;
- przycisk anulowania tłumaczenia bez utraty ukończonych partii;
- główna lista zawierająca tylko pobrane i kompletne modele AI;
- wspólny filtr obsługiwanych plików oraz filtr **Wszystkie pliki (*.*)**;
- informacje o postaciach, płci, relacjach i stylu jako dodatkowy kontekst;
- edytor pokazujący oryginał i tłumaczenie obok siebie;
- oznaczanie kwestii z możliwie niejednoznaczną płcią lub odmianą;
- interfejs graficzny oraz wersja terminalowa;
- oryginalny plik nigdy nie jest nadpisywany.

## Tryby tłumaczenia

| Tryb | Działanie | Najlepsze zastosowanie |
|---|---|---|
| **Tłumacz automatycznie** | Tłumaczy cały plik bez zatrzymywania i od razu zapisuje wynik. | Szybki rezultat i napisy do późniejszej korekty. |
| **Tłumacz z weryfikacją** | Używa dodatkowego kontekstu i otwiera edytor z oznaczonymi kwestiami. | Dialogi wymagające poprawnej płci, odmiany i spójności postaci. |

## Interfejs i motywy

W sekcji **Ustawienia → Wygląd aplikacji** można przełączać się między dwoma układami bez
utraty wybranego pliku, języków, modelu ani wpisanego kontekstu:

- **Nowoczesny** — domyślny układ z nieruchomym panelem bocznym, skrótami do pięciu sekcji,
  kartami ustawień i stale widocznym paskiem postępu;
- **Klasyczny 0.4.7** — zachowany przewijany układ poprzedniego wydania.

Motyw zmienia się natychmiast, a wybrany interfejs i kolory są zapisywane dla następnych
uruchomień. Dostępne motywy to: Automatyczny — system, OLED Black, Midnight Blue, Graphite Pro,
Cyber Neon, Aurora Violet, Emerald Matrix, Crimson Studio, Arctic Light oraz Warm Sand. Domyślny
jest czytelny **Midnight Blue**, a **OLED Black** używa prawdziwie czarnego tła.

## Czas wyświetlania napisów

Program oblicza potrzebny czas na podstawie długości przetłumaczonego tekstu. Nie przesuwa początku
żadnej wypowiedzi i nie łączy tekstów różnych postaci. Koniec starego napisu jest zawsze ograniczony
początkiem następnego; jeżeli w źródle napisy już na siebie nachodzą, profil czytelności skraca
poprzedni wpis. Gdy między kwestiami jest za mało miejsca, program zachowuje synchronizację i podaje
w podsumowaniu, ilu napisów nie dało się w pełni wydłużyć.

| Profil | Minimum | Tempo czytania | Zastosowanie |
|---|---:|---:|---|
| **Zalecane** | 1,5 s | maks. 17 znaków/s | Domyślny kompromis między synchronizacją a czytelnością. |
| **Krótsze — szybkie dialogi** | 1,0 s | maks. 20 znaków/s | Dynamiczne sceny i osoby szybko czytające. |
| **Dłuższe — wygodne czytanie** | 2,0 s | maks. 14 znaków/s | Spokojniejsze tempo i więcej czasu na przeczytanie. |
| **Oryginalne timestampy** | bez zmian | bez zmian | Dokładne zachowanie wszystkich czasów źródłowego SRT. |
| **Własne ustawienia** | 0,5–5,0 s | 8–30 znaków/s | Ręczne dopasowanie do swoich preferencji. |

W trybach czytelności pojedynczy napis jest wydłużany tylko w ramach wolnego miejsca i ograniczonego
limitu. Jeśli dwa wpisy zaczynają się dokładnie jednocześnie, program zgłasza ten nierozwiązywalny
konflikt zamiast przesunąć dialog, połączyć postacie albo stworzyć nakładanie.

## Silniki

| Silnik | Internet | Klucz | Obsługa języków | Uwagi |
|---|---:|---:|---|---|
| **20 lokalnych modeli AI** | tylko przy pobieraniu dodatku | nie | zależnie od modelu | Działają lokalnie; użytkownik sam wybiera i usuwa modele. |
| **DeepL API** | tak | tak | zgodnie z aktualną ofertą API | Lepszy kontekst i jakość dla obsługiwanych par językowych. |

## Modele AI jako opcjonalne dodatki

Przycisk **Pobierz / usuń…** otwiera menedżer modeli. Żaden model tłumaczeniowy nie jest
wciskany do instalatora: użytkownik widzi szacowany rozmiar, wymagania RAM/VRAM i licencję, a
dopiero po potwierdzeniu pliki są pobierane z oficjalnego repozytorium Hugging Face. Przerwane
pobieranie można wznowić, a każdy model można później usunąć bez naruszania pozostałych.
Główne pole wyboru celowo pokazuje tylko modele, których stan to **Pobrany i gotowy**.
Nieukończony model pozostaje widoczny wyłącznie w menedżerze, gdzie można wznowić pobieranie.
Niedostępny punkt instalacji, uszkodzone dowiązanie albo pojedynczy wadliwy snapshot nie zamyka
GUI. Skaner pomija go, szuka innej kompletnej kopii i zapisuje szczegóły w
`%LOCALAPPDATA%\PolySub Translator\model-cache-diagnostics.log`. Gdy poprawnej kopii nie ma,
menedżer pokazuje stan **Cache niedostępny** i pozwala usunąć model przed ponownym pobraniem.
Na Windows nowe pobrania domyślnie korzystają z oficjalnego trybu Hugging Face bez symlinków,
aby nie odtwarzać problematycznego punktu instalacji.

Kolejność 1–20 jest orientacyjnym rankingiem ogólnej jakości, a nie gwarancją dla każdego języka.
Mały OPUS wyspecjalizowany w jednej parze może wypaść lepiej od większego modelu ogólnego właśnie
dla tej pary.

| # | Model | Pobieranie | Przeznaczenie | Licencja modelu |
|---:|---|---:|---|---|
| 1 | MADLAD-400 10B | ok. 43 GB | najwyższa jakość ogólna, bardzo mocny komputer | Apache-2.0 |
| 2 | MADLAD-400 7B | ok. 33,3 GB | najwyższa jakość ogólna | Apache-2.0 |
| 3 | MADLAD-400 3B | ok. 11,9 GB | bardzo wysoka jakość ogólna | Apache-2.0 |
| 4 | NLLB-200 3.3B | ok. 17,6 GB | bardzo wysoka, 196 języków | CC-BY-NC-4.0 |
| 5 | NLLB-200 Distilled 1.3B | ok. 5,5 GB | wysoka, lżejszy NLLB | CC-BY-NC-4.0 |
| 6 | NLLB-200 1.3B | ok. 5,5 GB | wysoka, 196 języków | CC-BY-NC-4.0 |
| 7 | M2M100 1.2B | ok. 4,9 GB | wysoka, około 100 języków | MIT |
| 8 | NLLB-200 Distilled 600M | ok. 2,5 GB | dobry kompromis rozmiaru i jakości | CC-BY-NC-4.0 |
| 9 | mBART-50 Many-to-Many | ok. 2,5 GB | tłumaczenie między 50 językami | sprawdź kartę modelu |
| 10 | M2M100 418M | ok. 1,9 GB | domyślny i zgodny ze starszym PolySub | MIT |
| 11 | mBART-50 English-to-Many | ok. 2,5 GB | angielski → obsługiwane języki | sprawdź kartę modelu |
| 12 | mBART-50 Many-to-English | ok. 2,5 GB | obsługiwane języki → angielski | sprawdź kartę modelu |
| 13 | OPUS English → Polish | ok. 320 MB | tylko angielski → polski | Apache-2.0 |
| 14 | OPUS Polish → English | ok. 320 MB | tylko polski → angielski | Apache-2.0 |
| 15 | OPUS German → Polish | ok. 320 MB | tylko niemiecki → polski | Apache-2.0 |
| 16 | OPUS Spanish → Polish | ok. 320 MB | tylko hiszpański → polski | Apache-2.0 |
| 17 | OPUS French → Polish | ok. 320 MB | tylko francuski → polski | Apache-2.0 |
| 18 | OPUS Ukrainian → Polish | ok. 320 MB | tylko ukraiński → polski | Apache-2.0 |
| 19 | OPUS Arabic → Polish | ok. 320 MB | tylko arabski → polski | Apache-2.0 |
| 20 | OPUS Japanese → Polish | ok. 320 MB | tylko japoński → polski | Apache-2.0 |

Modele NLLB są opublikowane jako modele badawcze na licencji **CC-BY-NC-4.0**, czyli do użytku
niekomercyjnego. Menedżer pokazuje tę informację przed pobraniem. Szczegółowe warunki zawsze
znajdują się pod przyciskiem **Karta i licencja modelu**.

## Automatyczne wykrywanie sprzętu

Lista urządzeń nie zawiera wpisanych na stałe modeli. Przy każdym uruchomieniu PolySub odczytuje
prawdziwą nazwę procesora i wszystkich kart graficznych obecnych w komputerze. Można wybrać:

- **Automatycznie — najlepsze dostępne urządzenie**;
- konkretną wykrytą kartę graficzną;
- konkretny procesor.

Program osobno sprawdza możliwość użycia urządzenia do lokalnego modelu i do rozpoznawania mowy. Obsługuje
backendy udostępnione przez zainstalowane środowisko, między innymi CUDA, ROCm i Intel XPU. Jeśli
wybrane GPU albo sterownik nie obsługuje danej operacji, PolySub informuje o tym i proponuje lub
automatycznie wykonuje zadanie na CPU. Awaria GPU podczas ładowania albo obliczeń również nie
powoduje utraty całego zadania — program ponawia operację na procesorze.

Instalator v0.5.3 zawiera PyTorch 2.11 z CUDA 12.8 i cuDNN 9 dla kart NVIDIA GTX 10 oraz
RTX 20/30/40/50, w tym RTX 2080, z aktualnym sterownikiem. Radeon wymaga innego wariantu
PyTorch. PolySub po wykryciu zgodnej karty sam dobiera jej architekturę, w tle pobiera własne
odizolowane środowisko Python oraz oficjalny PyTorch ROCm 7.14, a następnie wykonuje prawdziwe
mnożenie macierzy na GPU. Nie ma osobnego przycisku konfiguracji ani zależności od Pythona
zainstalowanego w systemie. RX 9070 XT jest automatycznie przypisywany do pakietu `gfx1201`.
Instalacja przygotowuje `setuptools.build_meta` i dopuszcza wymagany przez oficjalny indeks
źródłowy metapakiet `rocm`, dlatego przerwane środowisko z wcześniejszej wersji może zostać
automatycznie dokończone bez ręcznej instalacji Pythona.
Jeżeli procesor Ryzen udostępnia również zintegrowane Radeon Graphics, PolySub testuje każdy indeks
HIP osobno, izoluje RX 9070 XT przez `HIP_VISIBLE_DEVICES` i uruchamia ją jako `cuda:0` tylko
w prywatnym workerze. Nie wyłącza iGPU w BIOS-ie ani w Menedżerze urządzeń, więc może ono nadal
obsługiwać monitor. Pełny przebieg jest zapisywany w `%LOCALAPPDATA%\PolySub Translator\amd-runtime-diagnostics.log`.
Obsługiwane są aktualne oficjalne cele AMD dla RX 9000, RX 7000, wybranych RDNA2, Radeon PRO
i Radeonów w procesorach Ryzen. Karta bez oficjalnego pakietu lub z niezgodnym sterownikiem
pozostaje jawnie na CPU. AMD wymaga obecnie Windows 11 25H2 i zgodnego sterownika Adrenalin;
program nie modyfikuje sterownika systemowego. Przy wypalaniu filmu aplikacja może niezależnie
użyć AMD AMF lub Intel Quick Sync, jeśli udostępnia je FFmpeg.

Sekcja **Wykorzystanie procesora** mapuje wybrany procent na prawdziwą liczbę logicznych wątków.
Ustawienie 100% przekazuje wszystkie dostępne wątki do PyTorch, Whispera i kodera CPU oraz zwiększa
bezpieczny rozmiar partii tłumaczenia. Nie zmienia parametrów jakości modelu. Wskaźnik Menedżera
zadań może chwilowo spaść podczas pobierania, odczytu plików albo etapów, których nie da się
równolegle rozłożyć, ale program nie wykonuje sztucznego obciążenia bez użytecznej pracy.

Od wersji 0.4.9 oryginalny kod projektu jest udostępniany na warunkach
**PolyForm Noncommercial License 1.0.0**. Dozwolony jest użytek osobisty i inny niekomercyjny;
użytek zarobkowy lub inny komercyjny wymaga osobnej pisemnej zgody fgSousace. Wcześniejsze
wydania zachowują warunki, na których zostały opublikowane. Wagi modeli są pobierane osobno i
podlegają licencji widocznej w menedżerze oraz na oficjalnej karcie danego modelu.

## Dodatkowa funkcja: film zamiast gotowego SRT

Dotychczasowy wybór `.srt` działa tak samo jak wcześniej. Dodatkowo można wskazać cały film:

1. PolySub próbuje wyciągnąć pierwszą tekstową ścieżkę napisów do `film.extracted.srt`.
2. Jeżeli film nie ma tekstowych napisów, Whisper słucha audio i tworzy `film.transcribed.srt`.
3. Program wykrywa język utworzonego tekstu.
4. Użytkownik wybiera język docelowy i zwykły tryb tłumaczenia.
5. Wynik zostaje zapisany obok filmu, np. jako `film.pl.srt`.
6. Na końcu można wybrać szybkie dodanie przełączanej ścieżki albo wypalenie napisów na stałe
   w obrazie filmu.

Do ekstrakcji używany jest FFmpeg dołączony do aplikacji, więc nie trzeba instalować go ręcznie.
Rozpoznawanie mowy działa lokalnie i oferuje wariant **small** (szybszy) oraz **medium**
(dokładniejszy, ustawiony domyślnie). Model Whisper pobiera się tylko przy pierwszym użyciu danego
wariantu i pozostaje w pamięci podręcznej Windows.

> Whisper rozpoznaje wypowiedziane słowa i ich czas, ale nie zna automatycznie imion ani płci
> rozmówców. Do takich przypadków nadal służą informacje o postaciach i tryb weryfikacji.

### Szybkie dołączanie napisów do filmu

PolySub nie przelicza ponownie obrazu ani dźwięku. FFmpeg kopiuje istniejące strumienie 1:1 i
dodaje przełączaną ścieżkę napisów. Dlatego karta graficzna nie jest potrzebna, jakość filmu się
nie zmienia, a operacja jest ograniczona głównie szybkością odczytu i zapisu dysku. Zależnie od
kontenera powstaje np. `film.pl.subtitled.mp4` albo `film.pl.subtitled.mkv`.

Napisy można włączać i wyłączać w odtwarzaczu. Nie są one wypalane na stałe w każdej klatce — takie
wypalanie jest dostępne jako drugi, osobny przycisk.

### Trwałe napisy na obrazie do telewizora

Przycisk **Wypal napisy na obrazie — TV** tworzy osobny plik, domyślnie
`film.pl.burned.mp4`. Tekst staje się częścią każdej klatki, więc będzie widoczny również w
odtwarzaczu lub telewizorze, który nie włącza dodatkowej ścieżki SRT.

Ta operacja musi ponownie zakodować obraz. PolySub najpierw sprawdza dostępne kodery i próbuje
NVIDIA NVENC, Intel Quick Sync albo AMD AMF zgodnie z wybranym sprzętem. Jeśli koder sprzętowy jest
niedostępny lub zgłosi błąd, program automatycznie przechodzi na wielowątkowy x264 na CPU. Obraz
jest zapisywany jako H.264 z formatem pikseli `yuv420p`, a dźwięk jako AAC dla szerokiej zgodności
z telewizorami. Pasek pokazuje przetworzony czas filmu, a oryginał nigdy nie jest nadpisywany.

PolySub pracuje na zwykłym lokalnym pliku wideo. Nie przechwytuje filmu bezpośrednio z aplikacji
HBO ani nie obchodzi zabezpieczeń DRM — najpierw trzeba mieć legalnie dostępny, niechroniony plik,
który można otworzyć w programie.

## Najprostsza instalacja na Windows

Nie musisz instalować Pythona, Gita ani wpisywać komend. Instalator pobiera się bezpośrednio z
zakładki **Releases** — bez szukania workflow i rozpakowywania dodatkowego artefaktu:

1. Otwórz [najnowszą wersję PolySub Translator](https://github.com/FgSousace/PolySub-Translator/releases/latest).
2. W sekcji **Assets** wybierz jeden z dwóch wariantów:
   - `PolySub-Translator-Setup-0.5.3.exe` — uruchamiasz bezpośrednio, bez rozpakowywania;
   - `PolySub-Translator-Installer-0.5.3.zip` — po rozpakowaniu zawiera instalator i `README.txt`.
3. Uruchom `PolySub-Translator-Setup-0.5.3.exe` i wybierz katalog instalacji.
4. Zostaw zaznaczoną opcję utworzenia ikony na pulpicie i kliknij **Instaluj**.
5. Po instalacji kreator pokaże krótką instrukcję, opcję uruchomienia programu oraz opcjonalne
   pole **Wybierz i pobierz modele AI**.

Przy kolejnych uruchomieniach klikaj skrót **PolySub Translator** na pulpicie albo w menu Start.
Instalator działa dla bieżącego użytkownika i nie wymaga uprawnień administratora.

Wersje od 0.4.6 są większe od 0.4.5, ponieważ zawierają biblioteki CUDA i cuDNN potrzebne do działania
na zgodnych kartach NVIDIA bez ręcznego instalowania środowiska programistycznego CUDA. Starsze
wydania 0.4.8, 0.4.7, 0.4.6, 0.4.5 oraz 0.4.4 pozostają dostępne na stronie Releases.

Po uruchomieniu program dyskretnie sprawdza najnowsze wydanie na GitHubie. Jeśli jest dostępna
nowsza wersja, pokaże jej numer i przycisk **Pobierz wersję…**. Instalator nigdy nie uruchamia się
sam — pobieranie rozpoczyna się dopiero po kliknięciu przycisku przez użytkownika.

> Windows może pokazać ostrzeżenie SmartScreen, ponieważ projekt nie ma jeszcze publicznie
> zaufanego certyfikatu podpisu kodu. Każdy build jest tworzony bez UPX, skanowany Microsoft
> Defenderem na runnerze Windows (gdy usługa jest dostępna) i otrzymuje sumy SHA-256. Jeśli
> Defender poda nazwę konkretnego zagrożenia lub PUA, nie wyłączaj ochrony — porównaj sumę pliku
> z `SHA256SUMS.txt` i zgłoś nazwę detekcji w Issues, aby plik mógł zostać przekazany Microsoftowi
> do ponownej analizy.

### Pierwsze tłumaczenie lokalne

Plik programu `.exe` zawiera silnik potrzebny do uruchomienia aplikacji, ale nie zawiera dużych
wag językowych. Otwórz **Pobierz / usuń…**, wybierz jeden z 20 modeli i sprawdź jego wymagania.
Domyślny M2M100 418M pobiera około 1,9 GB, a najmniejsze modele OPUS około 320 MB. Wybrany model
zostaje w pamięci podręcznej Windows, więc przy następnym tłumaczeniu nie jest pobierany ponownie.

### Wersja przenośna

Ze względu na dołączenie bibliotek CUDA wydania 0.4.6–0.5.3 nie zawierają nowej paczki portable, która
przekraczałaby limit pojedynczego pliku GitHub Releases. Wersja przenośna 0.4.5 nadal pozostaje
dostępna w historii wydań. Nowe wersje są publikowane jako `Setup.exe` i ZIP z instalatorem.

## Instalacja z kodu źródłowego na Windows

Wymagany jest Python 3.10 lub nowszy.

```powershell
git clone https://github.com/FgSousace/PolySub-Translator.git
cd PolySub-Translator
py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Wariant lokalny

```powershell
pip install "torch==2.11.0" --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[local,fasttext,video]"
polysub-gui
```

Model wybiera się w menedżerze w aplikacji; można też użyć `polysub --list-models`. Opcjonalny
fastText zwiększa zakres
automatycznego rozpoznawania do 176 języków; bez niego działa lekki mechanizm zapasowy. Dodatek
`video` zawiera obsługę FFmpeg i lokalnej transkrypcji Whisper.

### Wariant DeepL API

```powershell
pip install -e ".[video,fasttext]"
polysub-gui
```

Klucz można wpisać bezpośrednio w aplikacji — jest używany tylko w bieżącej sesji i nie jest
zapisywany. Alternatywnie ustaw `DEEPL_API_KEY` jako zmienną środowiskową. Jeśli nie potrzebujesz
funkcji filmu, wystarczy podstawowe `pip install -e .`.

## Użycie

### Interfejs graficzny

```powershell
polysub-gui
```

1. Kliknij **Wyszukaj napisy w filmie lub wybierz plik** i wskaż SRT albo film.
2. Dla filmu bez napisów wybierz szybszy lub dokładniejszy wariant Whisper.
3. Sprawdź automatycznie wykryty język i wybierz język docelowy.
4. Wybierz lokalny AI albo DeepL API; przyciskiem **Pobierz / usuń…** zarządzaj 20 modelami.
5. Zaznacz wymagany checkbox **Tłumacz automatycznie** albo **Tłumacz z weryfikacją**.
6. Zostaw **Automatycznie** albo wybierz wykryty procesor lub kartę graficzną.
7. Wybierz limit wykorzystania procesora; domyślne 100% daje maksymalną wydajność.
8. Wybierz czas napisów; domyślne **Automatyczna czytelność — zalecane** nie dopuszcza nakładania.
9. Opcjonalnie wpisz informacje, np. `Anna — kobieta; Marek — mężczyzna`.
10. Rozpocznij tłumaczenie; w razie potrzeby użyj **Anuluj tłumaczenie**, aby zachować postęp.
11. Dla filmu wybierz **Dodaj przełączaną ścieżkę — szybko** albo
    **Wypal napisy na obrazie — TV**.

Wynik tłumaczenia otrzyma nazwę w rodzaju `film.pl.srt`. W trybie weryfikacji zostanie najpierw
otwarty edytor. Przycisk dołączania uaktywnia się dopiero po zapisaniu gotowych napisów.

### Terminal

```powershell
# Wyświetlenie rankingu, rozmiarów, licencji i stanu 20 modeli
polysub --list-models

# Lokalnie: automatyczne wykrycie angielskiego i tłumaczenie na polski
polysub film.srt --target pl --engine local --mode automatic

# Użycie lekkiego modelu wyspecjalizowanego w angielski → polski
polysub film.srt --source en --target pl --engine local --local-model opus-en-pl

# DeepL i ręczna kontrola oznaczonych kwestii
$env:DEEPL_API_KEY = "TWÓJ_KLUCZ"
polysub film.srt --target pl --engine deepl --mode review

# Informacje o postaciach z pliku tekstowego
polysub film.srt --target pl --engine deepl --mode review --context-file postacie.txt

# Dłuższe napisy albo własne tempo 13 znaków na sekundę i minimum 2,3 sekundy
polysub film.srt --target pl --subtitle-timing comfortable
polysub film.srt --target pl --subtitle-timing custom --minimum-subtitle-seconds 2.3 --subtitle-cps 13

# Cały film: wyciągnięcie napisów lub transkrypcja audio, a następnie tłumaczenie
polysub film.mp4 --target pl --engine local --speech-model medium

# To samo oraz szybkie utworzenie filmu z przełączaną polską ścieżką napisów
polysub film.mp4 --target pl --engine local --attach-to-video

# Film z polskimi napisami wypalonymi na stałe i pełnym limitem CPU
polysub film.mp4 --target pl --engine local --burn-into-video --cpu-limit 100
```

Uruchomienie `polysub` bez parametrów otwiera GUI.

## Dokładność płci i odmiany

Samo zdanie `I'm ready` nie zawiera informacji, czy mówi kobieta, czy mężczyzna. Żaden translator
nie może zawsze odtworzyć tej informacji, jeżeli nie występuje ona w napisach albo kontekście.
Dlatego PolySub:

1. analizuje sąsiednie kwestie;
2. pozwala podać profile postaci;
3. oznacza potencjalnie niejednoznaczne fragmenty;
4. umożliwia poprawienie każdej kwestii przed zapisaniem.

Tryb weryfikacji zwiększa kontrolę nad jakością, ale nie udaje stuprocentowej pewności tam, gdzie
tekst źródłowy nie zawiera wymaganej informacji.

## Bezpieczeństwo pliku

- oryginalny plik nie jest modyfikowany;
- oryginalny film nigdy nie jest modyfikowany ani nadpisywany;
- napisy wyciągnięte lub rozpoznane z filmu są zapisywane w osobnym pliku roboczym `.srt`;
- film z dołączonymi napisami zawsze jest zapisywany jako osobny plik `.mp4` albo `.mkv`;
- film z napisami wypalonymi na obrazie również powstaje jako osobny plik;
- liczba kwestii, identyfikatory i początki wypowiedzi są sprawdzane przed zapisem;
- profile czytelności nigdy nie przedłużają starego napisu na początek następnej wypowiedzi;
- niedokończone zadanie trafia do pliku `*.srt.polysub.json`;
- plik awaryjny nie zawiera klucza API i jest usuwany po ukończeniu tłumaczenia;
- `.env` oraz pliki awaryjne są ignorowane przez Git.

## Testy i jakość kodu

```powershell
pip install -e ".[dev]"
ruff check .
pytest
```

GitHub Actions uruchamia lint i testy na Pythonie 3.10 oraz 3.12. Workflow Windows buduje
`Setup.exe`, instaluje go w czystym katalogu, sprawdza dołączony README, katalog 20 modeli, profile
czasu bez nakładania, oba sposoby dodawania napisów, ustawienia CPU, biblioteki CUDA/cuDNN, GUI,
deinstalator i zawartość ZIP-a,
a dopiero potem publikuje pliki w Releases.

## Struktura projektu

```text
src/polysub/
├── engines/       # DeepL i pięć rodzin lokalnych modeli AI
├── cli.py         # interfejs terminalowy
├── gui.py         # aplikacja desktopowa
├── translation_models.py # katalog 20 modeli i mapy języków
├── model_downloads.py    # bezpieczne pobieranie, wznawianie i usuwanie
├── service.py     # tłumaczenie, kontekst, postęp i wznowienie
├── performance.py # limity CPU i konfiguracja bibliotek wielowątkowych
├── subtitle_timing.py # profile czytelności i ochrona przed nakładaniem
├── subtitles.py   # parser oraz walidacja SRT
├── video.py       # FFmpeg, wbudowane napisy i lokalna transkrypcja Whisper
├── detector.py    # automatyczne wykrywanie języka
└── review.py      # wyszukiwanie fragmentów wymagających kontroli
```

## Plan rozwoju

- obsługa VTT i ASS/SSA;
- tłumaczenie całych folderów;
- słownik nazw i terminów zapisywany per projekt;
- profile postaci przypisywane do konkretnych rozmówców;
- pamięć zaakceptowanych tłumaczeń;
- podpis cyfrowy instalatora Windows certyfikatem code-signing.

## Licencja i autor

PolySub Translator™ został stworzony przez **fgSousace**.

Required Notice: PolySub Translator™ — Copyright © 2026 fgSousace. Licensed for noncommercial use only.

Kod od v0.4.9: [PolyForm Noncommercial License 1.0.0](LICENSE). Informacje o wymaganym oznaczeniu
znajdują się w [NOTICE.txt](NOTICE.txt), a licencje bibliotek i modeli w
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Pełna instrukcja:
[docs/INSTRUKCJA_OBSLUGI_PL.md](docs/INSTRUKCJA_OBSLUGI_PL.md).
