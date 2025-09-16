import os
from openai import OpenAI
import dotenv

# Upewnij się, że masz ustawiony klucz:
# export OPENAI_API_KEY="twój_klucz_api"
dotenv.load_dotenv()
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Tekst wyroku do testów
judgment_text = """
I SA/Gd 515/25 - Postanowienie WSA w Gdańsku

Data orzeczenia
2025-09-15 orzeczenie nieprawomocne
Data wpływu
2025-07-14
Sąd
Wojewódzki Sąd Administracyjny w Gdańsku
Sędziowie
Irena Wesołowska /przewodniczący sprawozdawca/
Symbol z opisem
6115 Podatki od nieruchomości, w tym podatek rolny, podatek leśny oraz łączne zobowiązanie pieniężne
Hasła tematyczne
Umorzenie postępowania
Skarżony organ
Samorządowe Kolegium Odwoławcze
Treść wyniku
Umorzono postępowanie
Powołane przepisy
Dz.U. 2024 poz 935 art. 161 par. 1 pkt 3
Ustawa z dnia 30 sierpnia 2002 r. Prawo o postępowaniu przed sądami administracyjnymi (t. j.)
Sentencja
Dnia 15 września 2025 roku Wojewódzki Sąd Administracyjny w Gdańsku w składzie następującym: Przewodniczący: Sędzia WSA Irena Wesołowska po rozpoznaniu w dniu 15 września 2025 r. na posiedzeniu niejawnym sprawy ze skargi B.S. na decyzję Samorządowego Kolegium Odwoławczego w Gdańsku z dnia 16 kwietnia 2025 r., sygn. akt SKO Gd/4183/24 w przedmiocie podatku od nieruchomości za 2024 rok postanawia umorzyć postępowanie

Uzasadnienie
B.S. pismem z 16 czerwca 2025 r. złożyła skargę na decyzję Samorządowego Kolegium Odwoławczego w Gdańsku w przedmiocie podatku od nieruchomości za 2024 rok.

W piśmie z 11 sierpnia 2025 r. B.S. oświadczyła, że nie składała skargi do Wojewódzkiego Sądu Administracyjnego w Gdańsku, a pismo z 16 czerwca
2025 r. było wnioskiem, żądaniem, skierowanym do Prezydenta Miasta Gdyni oraz do wiadomości Samorządowego Kolegium Odwoławczego w Gdańsku.

(... skrócone dalsze uzasadnienie ...)
"""

# Prompt taki sam jak w Twoim kodzie
analysis_prompt = """Na podstawie poniższego orzeczenia sądowego przygotuj artykuł do newslettera prawniczego w następującym formacie i stylu.

Format i styl (BEZWZGLĘDNIE PRZESTRZEGAJ):
- Pierwsza linia to sam atrakcyjny tytuł (maksymalnie 80 znaków), bez żadnych prefiksów typu "Tytuł:"; tytuł ma być w formacie "**{tytuł}**"
- Następnie napisz jeden ciągły tekst analityczny z podziałem na akapity. Aby zacząć nowy akapit użyj jednego znaku nowej linii (Enter).
- bez nagłówków, wypunktowań i śródtytułów.
- Ostatnia linia musi zaczynać się od nowej linii i dosłownie od: "Sygnatura: " i zawierać sygnaturę, sąd i datę orzeczenia. np. "I SA/Gd 515/25, WSA w Gdańsku, 15 września 2025 r." i nic więcej
- Zachowaj formalny, profesjonalny ton. Nie dodawaj metakomentarzy ani uwag o instrukcjach.
- Dla każdego punktu z "Treść analizy" poniżej napisz oddzielny akapit.


Treść analizy (wpleciona naturalnie w narrację):
- Krótki wstęp (2–3 zdania) wyjaśniający, czego dotyczy sprawa i dlaczego jest istotna.
- Zwięzły, precyzyjny opis stanu faktycznego.
- Analiza prawna z powołaniem zastosowanych przepisów i podstaw rozstrzygnięcia.
- Argumenty stron oraz uzasadnienie sądu.
- Ocena, czy orzeczenie jest nowatorskie, czy mieści się w utrwalonej linii orzeczniczej.
- Praktyczne znaczenie wyroku (dla gmin, firm, osób fizycznych) 
- Wskazanie ryzyk wynikających z wyroku
- Wskazanie dobrych praktyk wynikających z wyroku

W razie braku informacji w materiale źródłowym — nie wymyślaj, pomiń.
PAMIĘTAJ - Całość twojej odpowiedzi musi bezwzględnie mieścić się w przedziale od 360 do 380 słów.

Orzeczenie do analizy:
"""

# Zbudowanie pełnego promptu
full_prompt = analysis_prompt + judgment_text

response = client.responses.create(
    model="gpt-5-nano",
    instructions="Jesteś ekspertem prawa administracyjnego. Generujesz odpowiedzi po Polsku",
    input=analysis_prompt + judgment_text,
    reasoning={"effort": "low"},
    text={"verbosity": "low"},
)

input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens

cost_input = input_tokens * 0.00000005   # 0.050 / 1_000_000
cost_output = output_tokens * 0.0000004  # 0.400 / 1_000_000

total_cost = cost_input + cost_output

print(f"Koszt: {total_cost:.6f} USD")

print("\n=== Wygenerowane podsumowanie ===\n")
text = response.output[1].content[0].text

# usunięcie pustych linii
clean_text = "\n".join(line for line in text.splitlines() if line.strip())

print(clean_text)
