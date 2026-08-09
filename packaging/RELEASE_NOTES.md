## Nowości w wersji 0.4.7

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

1. Pobierz `PolySub-Translator-Setup.exe`.
2. Uruchom plik, wybierz katalog i kliknij **Instaluj**.

### Instalator w ZIP-ie

1. Pobierz `PolySub-Translator-Installer.zip`.
2. Rozpakuj go — w środku są `PolySub-Translator-Setup.exe` i `README.txt`.
3. Uruchom instalator.

Po instalacji kreator pokazuje krótką instrukcję i pozwala od razu uruchomić program. Skrót
**PolySub Translator** jest dostępny na pulpicie oraz w menu Start.

Nie pobieraj plików `Source code`, jeżeli chcesz po prostu uruchomić program.

Windows SmartScreen może wyświetlić ostrzeżenie, ponieważ instalator nie ma jeszcze płatnego
certyfikatu podpisu cyfrowego. W takim przypadku wybierz **Więcej informacji → Uruchom mimo to**.

Instalator nie wymaga Pythona, Gita ani uprawnień administratora. Wydania 0.4.6 i 0.4.7 nie zawierają nowej
paczki portable, ponieważ dołączone biblioteki CUDA przekroczyłyby limit pojedynczego pliku GitHub
Releases. Portable z wersji 0.4.5 nadal pozostaje dostępne w historii wydań.
