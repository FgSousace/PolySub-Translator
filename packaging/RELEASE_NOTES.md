## PolySub Translator 0.5.4

- dodano **polskiego lektora Chatterbox Multilingual V3**: jeden głos czyta gotowe polskie
  napisy, a FFmpeg miesza go z oryginalnym dźwiękiem ściszonym do 28% bez ponownego
  kodowania obrazu;
- Chatterbox działa w prywatnym, odizolowanym środowisku CPU, dzięki czemu jego wymagany
  PyTorch 2.6 nie koliduje z PyTorch 2.11/CUDA aplikacji ani z osobnym ROCm AMD;
- menedżer ma osobne zakładki **Tłumaczenie**, **Whisper** i **Lektor**;
- pobieranie pokazuje prawdziwy postęp: procent oraz zapisane MB/GB względem całego modelu;
- katalog tłumaczeń nie oferuje już modeli 11,9–43 GB; największy dodatek ma około
  5,5 GB, a najmniejsze modele OPUS około 300 MB;
- dodano sprawdzone modele OPUS dla polski↔niemiecki, polski↔hiszpański oraz
  litewski/norweski→polski;
- każdy model ma widoczną ocenę dokładności 1–5 i opis najlepszego zastosowania;
- Whisper ma sześć zarządzanych wariantów od Tiny do Large v3; główne okno pokazuje
  wyłącznie modele rzeczywiście pobrane;
- poprawiono rozpoznawanie mowy przez dokładniejsze wyszukiwanie wiązki, cierpliwość
  dekodera, dopracowany filtr VAD i progi odrzucania halucynacji;
- dodano test paczki Windows dla katalogów modeli, workera Chatterbox i synchronizacji WAV.

## Pobieranie

- **Setup EXE:** pobierz `PolySub-Translator-Setup-0.5.4.exe` i uruchom instalator.
- **ZIP z instalatorem:** pobierz `PolySub-Translator-Installer-0.5.4.zip`, rozpakuj i uruchom
  znajdujący się w środku plik Setup.
- **Sumy kontrolne:** `SHA256SUMS.txt` pozwala zweryfikować pobrany plik.

Modele są opcjonalne i nie powiększają instalatora. Chatterbox pobiera tylko sześć plików
potrzebnych wariantowi Multilingual V3, a nie wszystkie historyczne wagi repozytorium.
