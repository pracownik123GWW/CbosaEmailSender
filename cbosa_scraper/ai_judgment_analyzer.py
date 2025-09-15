import os
import logging
from typing import List, Dict, Optional
from striprtf.striprtf import rtf_to_text
from openai import OpenAI
import regex

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
class JudgmentAnalyzer:
    def __init__(self):
        """Initialize the AI judgment analyzer."""
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = OpenAI(api_key=self.openai_api_key)
        self.logger = logging.getLogger(__name__)
        self.no_uzasadnienie_count = 0
        
        # Fixed prompt for newsletter analysis
        self.analysis_prompt = """Na podstawie poniższego orzeczenia sądowego przygotuj artykuł do newslettera prawniczego w następującym formacie:

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

Orzeczenie do analizy:
"""

    def extract_case_signature(self, rtf_content: str) -> Optional[str]:
        """Extract case signature (e.g., 'I SA/Po 188/25') from RTF content."""
        import re
        try:
            # Look for case signatures directly in RTF content first
            # Pattern for signatures like "I SA/Gl 81/25 - Wyrok"
            rtf_patterns = [
                r'([IVX]+\s+[A-Z]{2,4}\s+\d+[/]\d+)',            # III FZ 113/25, I FSK 625/24
                r'([IVX]+\s+S[A-Z]+[/][A-Za-z]+\s+\d+[/]\d+)',   # I SA/Gl 81/25
                r'([IVX]+\s+[A-Z]{2,4}[/][A-Za-z]+\s+\d+[/]\d+)', # II FPS/Gl 123/24
            ]
            
            for pattern in rtf_patterns:
                matches = re.findall(pattern, rtf_content, re.IGNORECASE)
                if matches:
                    signature = matches[0].strip()
                    signature = re.sub(r'\s+', ' ', signature)  # Normalize spaces
                    self.logger.info(f"Extracted case signature from RTF: {signature}")
                    return signature
            
            # Fallback: Extract plain text and search
            text = rtf_to_text(rtf_content)
            text_patterns = [
                r'([IVX]+\s+S[A-Z]+[/][A-Za-z]+\s+\d+[/]\d+)',   # I SA/Gl 81/25
                r'([IVX]+\s+[A-Z]{2,4}[/][A-Za-z]+\s+\d+[/]\d+)', # II FPS/Gl 123/24  
                r'([IVX]+\s+[A-Z]{2,4}\s+\d+[/]\d+)',            # I FSK 625/24
                r'([IVX]+\s+[A-Z]+[/\s]*[A-Za-z]*\s+\d+[/]\d+)', # General pattern
                r'(Sygn[.\s]*akt[:\s]*[IVX]+\s+[A-Z/\w\s]+\d+[/]\d+)', # Sygn. akt: pattern
            ]
            
            for pattern in text_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    signature = matches[0].strip()
                    signature = re.sub(r'\s+', ' ', signature)
                    signature = signature.replace('Sygn. akt:', '').strip()
                    self.logger.info(f"Extracted case signature from text: {signature}")
                    return signature
            
            self.logger.warning("No case signature found in RTF content")
            return None
            
        except Exception as e:
            self.logger.exception(f"Error extracting case signature: {e}")
            return None

    def extract_text_from_rtf(self, rtf_content: str) -> str:
        """Extract plain text from RTF content."""
        try:
            text = rtf_to_text(rtf_content)
            # Clean up the text
            text = text.strip()
            text = ' '.join(text.split())  # Normalize whitespace
            return text
        except Exception as e:
            self.logger.exception(f"Error extracting text from RTF: {e}")
            return rtf_content  # Fallback to original content

    def analyze_judgment(self, rtf_content: str, case_info: Optional[Dict] = None) -> Dict:
        """
        Analyze a single judgment using ChatGPT.
        
        Args:
            rtf_content: RTF content of the judgment
            case_info: Optional dictionary with case metadata (court, date, signature)
            
        Returns:
            Dictionary with analysis results
        """
        try:
            has_uz = JudgmentAnalyzer._has_uzasadnienie(rtf_content)
            if not has_uz:
                self.no_uzasadnienie_count += 1
                self.logger.info("Pominięto wywołanie API: brak uzasadnienia.")
                return {
                    "success": True,
                    "analysis": "Brak uzasadnienia w orzeczeniu - nie wygenerowano podsumowania",
                    "case_info": case_info or {},
                    "timestamp": None,
                    "tokens_used": 0,
                    "error": None,
                    "has_uzasadnienie": False,
                }
            
            # Extract plain text from RTF
            judgment_text = self.extract_text_from_rtf(rtf_content)
            
            # Prepare the full prompt using the single analysis prompt
            full_prompt = self.analysis_prompt + judgment_text
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {
                        "role": "system",
                        "content": "Jesteś ekspertem od prawa administracyjnego. Analizujesz orzeczenia sądów administracyjnych w Polsce i tworzysz szczegółowe biuletyny analityczne."
                    },
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ],
                max_completion_tokens=2000,
            )
            
            analysis_text = response.choices[0].message.content
            
            # Structure the response
            result = {
                "success": True,
                "analysis": analysis_text,
                "case_info": case_info or {},
                "timestamp": None,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "error": None
            }
            
            self.logger.info(f"Successfully analyzed judgment. Tokens used: {result['tokens_used']}")
            return result
            
        except Exception as e:
            self.logger.exception(f"Error analyzing judgment: {e}")
            return {
                "success": False,
                "analysis": None,
                "case_info": case_info or {},
                "timestamp": None,
                "tokens_used": 0,
                "error": str(e)
            }

    def analyze_multiple_judgments(self, judgments: List[Dict], progress_callback=None) -> List[Dict]:
        """
        Analyze multiple judgments with enhanced error handling and retry logic.
        
        Args:
            judgments: List of dictionaries containing RTF content and metadata
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of analysis results
        """
        results = []
        total_judgments = len(judgments)
        successful_analyses = 0
        
        self.logger.info(f"Starting analysis of {total_judgments} judgments")
        
        for i, judgment in enumerate(judgments, 1):
            self.logger.info(f"Analyzing judgment {i}/{total_judgments}")
            
            rtf_content = judgment.get('content', '')
            case_info = judgment.get('case_info', {})
            
            # Try analysis with retry logic
            result = self._analyze_with_retry(rtf_content, case_info, max_retries=2)
            result['judgment_number'] = i
            result['total_judgments'] = total_judgments
            
            results.append(result)
            
            # Update progress callback if provided
            if progress_callback:
                progress_callback(i, total_judgments, result['success'])
            
            # Log progress
            if result['success']:
                successful_analyses += 1
                self.logger.info(f"✓ Judgment {i}/{total_judgments} analyzed successfully")
            else:
                self.logger.exception(f"✗ Judgment {i}/{total_judgments} failed: {result['error']}")
        
        self.logger.info(f"Analysis complete. {successful_analyses}/{total_judgments} successful")
        return results

    def _analyze_with_retry(self, rtf_content: str, case_info: Optional[Dict] = None, max_retries: int = 2) -> Dict:
        """
        Analyze judgment with retry logic for failed requests.
        
        Args:
            rtf_content: RTF content of the judgment
            case_info: Optional dictionary with case metadata
            max_retries: Maximum number of retry attempts
            
        Returns:
            Dictionary with analysis results
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    self.logger.info(f"Retry attempt {attempt}/{max_retries}")
                    import time
                    time.sleep(1 * attempt)  # Progressive delay
                
                result = self.analyze_judgment(rtf_content, case_info)
                if result['success']:
                    return result
                else:
                    last_error = result['error']
                    
            except Exception as e:
                last_error = str(e)
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
        
        # All retries failed
        return {
            "success": False,
            "analysis": None,
            "case_info": case_info or {},
            "timestamp": None,
            "tokens_used": 0,
            "error": f"Failed after {max_retries} retries. Last error: {last_error}"
        }

    def calculate_analysis_stats(self, results: List[Dict]) -> Dict:
        """Calculate statistics from analysis results."""
        total_analyses = len(results)
        successful_analyses = sum(1 for r in results if r['success'])
        failed_analyses = total_analyses - successful_analyses
        
        total_tokens = sum(r.get('tokens_used', 0) for r in results)
        avg_tokens = total_tokens / total_analyses if total_analyses > 0 else 0
        
        # Rough cost estimation (GPT-4o pricing)
        cost_per_1k_tokens = 0.005  # $0.005 per 1K tokens (approximate)
        estimated_cost_usd = (total_tokens / 1000) * cost_per_1k_tokens
        estimated_cost_pln = estimated_cost_usd * 4.0  # Rough USD to PLN conversion
        
        return {
            'total_analyses': total_analyses,
            'successful_analyses': successful_analyses,
            'failed_analyses': failed_analyses,
            'success_rate': (successful_analyses / total_analyses * 100) if total_analyses > 0 else 0,
            'no_uzasadnienie_count': self.no_uzasadnienie_count,
            'total_tokens_used': total_tokens,
            'average_tokens_per_analysis': int(avg_tokens),
            'estimated_cost_usd': round(estimated_cost_usd, 4),
            'estimated_cost_pln': round(estimated_cost_pln, 2)
        }

    @staticmethod
    def _has_uzasadnienie(rtf: str) -> bool:
        """
        Wykrywa sekwencję RTF: \b Uzasadnienie\b0 (toleruje spacje/nowe linie, bez rozróżniania wielkości liter).
        """
        pattern = regex.compile(r'\\b\s*Uzasadnienie\s*\\b0')
        return bool(pattern.search(rtf))
