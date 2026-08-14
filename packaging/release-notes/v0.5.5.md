## PolySub Translator 0.5.5

- naprawiono uruchamianie wszystkich sześciu pobranych modeli Whisper na Windows;
- lokalna ścieżka snapshotu Whisper jest przekazywana do CTranslate2 jako zwykły tekst,
  więc import filmu nie kończy się błędem `incompatible constructor arguments`;
- naprawiono ładowanie **Chatterbox Multilingual V3** w faktycznie instalowanej wersji
  `chatterbox-tts==0.1.7`, która nie przyjmuje argumentu `t3_model` i domyślnie szuka V2;
- Chatterbox korzysta bezpośrednio z pobranych wag V3, bez kopiowania 3,25 GB i bez
  modyfikowania snapshotu Hugging Face;
- Whisper oraz Chatterbox pracują wyłącznie na lokalnych plikach i nie wymagają ponownego
  pobierania modeli po aktualizacji;
- dodano testy regresyjne dla ścieżki `WindowsPath` oraz obu wariantów API Chatterbox,
  a self-test instalatora odtwarza lokalne uruchomienie Whispera bez pobierania wag.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.5.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.5.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Modele pobrane w wersji 0.5.4 pozostają w cache i działają po aktualizacji do 0.5.5.
