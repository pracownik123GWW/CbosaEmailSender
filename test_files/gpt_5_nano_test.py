import os
from openai import OpenAI
import dotenv
import time
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

Wojewódzki Sąd Administracyjny w Gdańsku zważył, co następuje:

Postępowanie sądowe należało umorzyć.

Zgodnie z treścią art. 161 § 1 pkt 3 ustawy z dnia 30 sierpnia 2002 r. Prawo o postępowaniu przed sądami administracyjnymi (Dz. U. z 2024 r. poz. 935 z późn. zm.) - zwanej dalej: "p.p.s.a.", sąd wydaje postanowienie o umorzeniu postępowania, gdy postępowanie z innych przyczyn, niż cofnięcie skargi lub śmierć strony, stało się bezprzedmiotowe.

Bezprzedmiotowość postępowania sądowoadministracyjnego "z innych przyczyn" w rozumieniu powołanego przepisu zachodzi wtedy, gdy w toku postępowania, a przed wydaniem wyroku, przestaje istnieć przedmiot zaskarżenia.

W niniejszej sprawie skarżąca pismem z 16 czerwca 2025 r. złożyła skargę na decyzję Samorządowego Kolegium Odwoławczego w Gdańsku w przedmiocie podatku od nieruchomości za 2024 rok. Już po wszczęciu postępowania sądowoadministracyjnego skarżąca oświadczyła jednak, że nie składała skargi do sądu administracyjnego,

a wskazane pismo stanowiło wniosek kierowany do Prezydenta Miasta Gdyni oraz do wiadomości Samorządowego Kolegium Odwoławczego w Gdańsku.

Z powyższego oświadczenia zawartego w piśmie z 11 sierpnia 2025 r. wynika zatem, że intencją skarżącej nie było wszczynanie postępowania przed sądem administracyjnym, a zatem postępowanie takie nie może się toczyć.

Postępowanie sądowoadministracyjne wszczyna się w momencie skutecznego wniesienia skargi przez uprawniony podmiot. Z tego względu struktura tego postępowania ukształtowana jest jako spór prowadzony przed sądem przez podmiot żądający udzielenia ochrony prawnej i organ administracji publicznej, którego działanie lub zaniechanie stało się przyczyną zgłoszenia żądania udzielenia ochrony prawnej. Brak skargi oznacza, że sprawa nie może się toczyć, a Sąd nie jest władny do wydania merytorycznego rozstrzygnięcia sprawy. W takiej sytuacji uznać należy, że postępowanie sądowoadministracyjne jako bezprzedmiotowe należało umorzyć.

W tym stanie rzeczy Sąd, na mocy art. 161 § 1 pkt 3 p.p.s.a., orzekł jak w sentencji postanowienia.
"""

# Prompt taki sam jak w Twoim kodzie
analysis_prompt_1 = """
Na podstawie poniższego orzeczenia sądowego przygotuj artykuł do newslettera prawniczego w następującym formacie i stylu.

Format i styl (BEZWZGLĘDNIE PRZESTRZEGAJ):
- Pierwsza linia to sam atrakcyjny tytuł (maksymalnie 80 znaków), bez żadnych prefiksów typu "Tytuł:"; tytuł ma być w formacie "**{tytuł}**"
- Następnie napisz jeden ciągły tekst analityczny z podziałem na akapity. Aby zacząć nowy akapit użyj jednego znaku nowej linii (Enter).
- bez nagłówków, wypunktowań i śródtytułów.
- Ostatnia linia musi zaczynać się od nowej linii i dosłownie od: "Sygnatura: " i zawierać sygnaturę, sąd i datę orzeczenia. np. "I SA/Gd 515/25, WSA w Gdańsku, 15 września 2025 r." i nic więcej
- Zachowaj formalny, profesjonalny ton. Nie dodawaj metakomentarzy ani uwag o instrukcjach.
- Dla każdego punktu z "Treść analizy" poniżej napisz oddzielny akapit ale nie wpisuj tytułów akapitów z dwukropkiem lub myślnikiem. Pisz jako ciągły tekst


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
PAMIĘTAJ - Całość twojej odpowiedzi musi bezwzględnie mieścić się w przedziale od 300 do 350 słów.

Orzeczenie do analizy:
"""


# Test o4
analysis_prompt_2 = """
Na podstawie poniższego orzeczenia sądowego przygotuj artykuł do newslettera prawniczego w następującym formacie:

Zacznij od atrakcyjnego tytułu (maksymalnie 80 znaków) umieszczonego w nagłówku.

Następnie napisz ciągły, płynny tekst analityczny bez nagłówków sekcji. Tekst powinien zawierać wszystkie poniższe elementy wplecione naturalnie w narrację:

- Zaciekawiający wstęp (2-3 zdania) wyjaśniający czego dotyczy sprawa i dlaczego jest istotna
- Stan faktyczny opisany w uproszczeniu ale precyzyjnie
- Analizę prawną z zastosowanymi przepisami i podstawami prawnymi
- Argumenty stron i uzasadnienie sądu
- Informację czy orzeczenie jest nowatorskie czy opiera się na ugruntowanej linii orzeczniczej
- Praktyczne znaczenie wyroku (dla gmin, firm, osób fizycznych)
- Ryzyka lub dobre praktyki wynikające z orzeczenia
- Na końcu sygnaturę sprawy, sąd i datę wyroku

Pisz profesjonalnie ale przystępnie jako jeden ciągły tekst bez podziału na sekcje. Unikaj nadmiaru formalizmów.
Zadbaj aby długość twojej odpowiedzi nigdy nie przekroczyła 390 słów!

Orzeczenie do analizy:
"""



def gpt5():
    full_prompt_1 = analysis_prompt_1 + judgment_text

    start = time.time_ns()

    response = client.responses.create(
        model="gpt-5-nano",
        instructions="Jesteś ekspertem prawa administracyjnego. Generujesz odpowiedzi po Polsku",
        input=full_prompt_1 + judgment_text,
        reasoning={"effort": "medium"},
        text={"verbosity": "low"},
    )

    print(f"Czas odpowiedzi: {(time.time_ns() - start)/1000_000_000} s")

    print("\n=== Wygenerowane podsumowanie 1 ===\n")
    text = response.output[1].content[0].text

    # usunięcie pustych linii
    clean_text = "\n".join(line for line in text.splitlines() if line.strip())

    print(clean_text)

def gpt4():
    full_prompt_2 = analysis_prompt_2 + judgment_text

    start = time.time_ns()
    response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Jesteś ekspertem od prawa administracyjnego. Analizujesz orzeczenia sądów administracyjnych w Polsce i tworzysz szczegółowe biuletyny analityczne."
                        },
                        {
                            "role": "user",
                            "content": full_prompt_2
                        }
                    ],
                    max_tokens=2000,
                    temperature=0.3,
                )
            
    print(f"Czas odpowiedzi: {(time.time_ns() - start)/1000_000_000} s")
    analysis_text = response.choices[0].message.content
    print("\n=== Wygenerowane podsumowanie 2 ===\n")
    print(analysis_text)


gpt4()
