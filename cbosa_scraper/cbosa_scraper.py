import requests
from bs4 import BeautifulSoup
import time
import logging
from urllib.parse import urljoin
from cbosa_scraper.date_filter_manager import DateFilterManager
import json
from http.client import RemoteDisconnected
import random


class CBOSAScraper:
    """Scraper for CBOSA (Central Database of Administrative Court Judgments)"""

    def __init__(self, delay_between_requests=1.0):
        self.base_url = "https://orzeczenia.nsa.gov.pl"
        self.search_url = f"{self.base_url}/cbo/query"
        self.search_action_url = f"{self.base_url}/cbo/search"  # Actual search submission endpoint
        self.delay = delay_between_requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.date_filter = DateFilterManager()
        self.logger = logging.getLogger(__name__)

    def _get_with_retry(self, url, *, retries=4, backoff=1.6, timeout=(5, 40)):
        """
        GET z retry dla błędów sieciowych/5xx/429. Zwraca requests.Response.
        """
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                r = self.session.get(url, timeout=timeout)
                # retry dla 5xx i 429
                if r.status_code == 429 or (500 <= r.status_code < 600):
                    raise requests.HTTPError(f"{r.status_code} Server/Rate Limit", response=r)
                return r
            except (requests.ConnectionError, requests.Timeout, RemoteDisconnected, requests.HTTPError) as e:
                last_err = e
                if attempt == retries:
                    raise
                base_sleep = (backoff ** (attempt - 1))
                jitter = random.uniform(0, 0.4)
                extra = 1.5 if isinstance(e, requests.HTTPError) and getattr(e, "response", None) is not None and e.response.status_code == 429 else 0.0
                time.sleep(base_sleep + jitter + extra)
        raise last_err
    
    def search_cases(self, search_params, max_results=100):
        """
        Search for cases using the provided parameters
        Returns list of case URLs
        """
        try:
            self.logger.info(
                "Starting search with params:\n%s",
                json.dumps(search_params, indent=2, ensure_ascii=False))

            # Extract and validate date parameters
            date_from_str = search_params.get('date_from', '')
            date_to_str = search_params.get('date_to', '')

            date_filter_info = None
            if date_from_str or date_to_str:
                try:
                    date_filter_info = self.date_filter.prepare_cbosa_dates(
                        date_from_str, date_to_str)
                    self.logger.info(
                        f"Date filtering enabled: {self.date_filter.get_date_filter_summary(date_from_str, date_to_str)}"
                    )
                except ValueError as e:
                    self.logger.exception(f"Date validation error: {e}")
                    raise

            # First, get the search form to understand its structure
            response = self._get_with_retry(self.search_url, retries=4, backoff=1.6, timeout=(5, 30))
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Prepare form data based on the original form structure
            form_data = self._prepare_form_data(search_params, soup)

            # Add date parameters to CBOSA form if provided
            if date_filter_info and date_filter_info['cbosa_params']:
                form_data.update(date_filter_info['cbosa_params'])
                self.logger.info(
                    f"Added CBOSA date params: {date_filter_info['cbosa_params']}"
                )

            # Submit search to the correct endpoint
            time.sleep(self.delay)
            search_response = self.session.post(self.search_action_url,
                                                data=form_data)
            search_response.raise_for_status()

            # Parse search results with pagination
            case_data = self._parse_all_search_results(search_response.content,
                                                       search_response.url,
                                                       max_results)

            self.logger.info(
                f"Found {len(case_data)} cases from CBOSA (before local filtering)"
            )

            # Skip local date filtering - CBOSA handles date filtering correctly
            # The signature year (e.g., /24) doesn't necessarily match the judgment date
            self.logger.info("Using CBOSA's date filtering results without additional local filtering")

            self.logger.info(
                f"Final result: {len(case_data)} cases after all filtering")
            return case_data

        except Exception as e:
            self.logger.exception(f"Error in search_cases: {str(e)}")
            raise

    def _prepare_form_data(self, search_params, soup):
        """Prepare form data matching the original CBOSA form structure"""
        form_data = {}

        # Find the form and extract any hidden fields
        form = soup.find('form')
        if form:
            for input_tag in form.find_all('input', type='hidden'):
                name = input_tag.get('name')
                value = input_tag.get('value', '')
                if name:
                    form_data[name] = value

        # Map our search parameters to CBOSA form fields
        # Based on actual browser network capture - must match exactly
        field_mapping = {
            'keywords': 'wszystkieSlowa',
            'keywords_location': 'wystepowanie',
            'with_inflection': 'odmiana',
            'signature': 'sygnatura',
            'court': 'sad',
            'judgment_type':
            'rodzaj',  # Maps to 'Wyrok', 'Postanowienie', 'Uchwała'
            'case_symbol': 'symbole',
            'judge': 'sedziowie',
            'judge_function': 'funkcja',
            'final_judgment': 'takPrawomocne',  # Checkbox: 'on' or empty
            'ending_judgment': 'takKonczace',  # Checkbox: 'on' or empty
            'with_thesis': 'takTezy',  # Checkbox: 'on' or empty
            'with_justification': 'takUzasadnienie',  # Checkbox: 'on' or empty
            'with_dissenting': 'takOdrebne',  # Checkbox: 'on' or empty
            'organ_type': 'rodzaj_organu',
            'thematic_tags': 'hasla',
            'legal_act': 'akty',
            'legal_provision': 'przepisy',
            'published': 'opublikowane',  # Checkbox: 'on' or empty
            'publication_details': 'publikacje',
            'with_commentary': 'glosowane',  # Checkbox: 'on' or empty
            'commentary_details': 'glosy'
        }

        # Set default values that browser always sends (from network capture)
        form_data.update({
            'wszystkieSlowa': '',  # Always empty in capture
            'wystepowanie': 'gdziekolwiek',  # Default location
            'sygnatura': '',  # Always empty
            'sad': 'dowolny',  # Default court value
            'symbole': '',  # Always empty
            'sedziowie': '',  # Always empty
            'funkcja': 'dowolna',  # Default judge function
            'rodzaj_organu': '',  # Always empty
            'akty': '',  # Always empty
            'przepisy': '',  # Always empty
            'publikacje': '',  # Always empty
            'glosy': ''  # Always empty
        })

        # Add search parameters (will override defaults)
        checkbox_fields = {
            'with_inflection', 'published', 'with_commentary',
            'final_judgment', 'ending_judgment', 'with_thesis',
            'with_justification', 'with_dissenting'
        }

        for param_key, form_key in field_mapping.items():
            value = search_params.get(param_key, '')
            if value:
                # Convert checkbox values: CBOSA expects "on" not "1" or "Tak"
                if param_key in checkbox_fields:
                    if value in ['1', 'Tak', 'on', True]:
                        form_data[form_key] = 'on'
                else:
                    # Special handling for thematic tags - browser adds exclamation mark
                    if param_key == 'thematic_tags':
                        form_data[form_key] = value + '!'
                    else:
                        form_data[form_key] = value

        # Log the final form data for debugging
        self.logger.info("Form data being sent to CBOSA:")
        for key, value in form_data.items():
            self.logger.info(f"  {key}: {value}")

        # Special debug for judgment type issue
        if 'rodzaj' in form_data:
            self.logger.info(
                f">>> JUDGMENT TYPE DEBUG: rodzaj = '{form_data['rodzaj']}'")
        else:
            self.logger.info(
                ">>> JUDGMENT TYPE DEBUG: 'rodzaj' field is MISSING from form data!"
            )
            self.logger.info(
                f">>> Original judgment_type parameter: '{search_params.get('judgment_type', 'NOT_SET')}'"
            )

        # Add required form submission field (submit button value)
        form_data[
            'submit'] = 'Szukaj'  # Submit button value from form analysis

        return form_data

    def _parse_search_results(self, content, max_results):
        """Parse search results page and extract case URLs with signatures"""
        soup = BeautifulSoup(content, 'html.parser')
        case_data = []

        # Look for links to individual cases
        # CBOSA typically shows results in a table or list format
        links = soup.find_all('a', href=True)

        for link in links:
            href = link.get('href')
            if href and 'doc' in href:
                # Check parent classes to distinguish primary results from related cases
                parent_classes = link.parent.get('class',
                                                 []) if link.parent else []

                # Only collect primary search results (blue links), exclude related cases (red links)
                if 'info-list-value' in parent_classes and 'powiazane' not in parent_classes:
                    full_url = urljoin(self.base_url, href)

                    # Extract case signature from link text or surrounding elements
                    signature = self._extract_signature_from_link(link, soup)

                    # Avoid duplicates by checking URL
                    if not any(case['url'] == full_url for case in case_data):
                        self.logger.info(
                            f"✅ Primary result: {signature} (parent classes: {parent_classes})"
                        )
                        case_data.append({
                            'url': full_url,
                            'signature': signature
                        })
                        if len(case_data) >= max_results:
                            break
                elif 'powiazane' in parent_classes:
                    signature = self._extract_signature_from_link(link, soup)
                    self.logger.info(
                        f"🔴 Skipping related case: {signature} (parent classes: {parent_classes})"
                    )
                else:
                    self.logger.debug(
                        f"⚪ Unknown link type: {href} (parent classes: {parent_classes})"
                    )

        # If no primary results found, look for alternative patterns but still respect class filtering
        if not case_data:
            self.loggerwarning(
                "No primary results found with 'info-list-value' class, checking alternative patterns..."
            )
            # Look for any links that might be case results, but still check parent classes
            for link in links:
                href = link.get('href')
                if href and '/cbo/' in href and href != '/cbo/query':
                    parent_classes = link.parent.get(
                        'class', []) if link.parent else []

                    # Still avoid related cases even in fallback mode
                    if 'powiazane' not in parent_classes:
                        full_url = urljoin(self.base_url, href)
                        signature = self._extract_signature_from_link(
                            link, soup)

                        if not any(case['url'] == full_url
                                   for case in case_data):
                            self.logger.info(
                                f"⚡ Fallback result: {signature} (parent classes: {parent_classes})"
                            )
                            case_data.append({
                                'url': full_url,
                                'signature': signature
                            })
                            if len(case_data) >= max_results:
                                break

        return case_data

    def _extract_signature_from_link(self, link, soup):
        """Extract case signature from link text or surrounding elements"""
        import re

        # First, check the link text itself
        link_text = link.get_text(strip=True)

        # Look for case signature patterns in the link text
        signature_patterns = [
            r'([IVX]+\s+[A-Z]{2,4}[/\s]*\w*\s+\d+[/]\d+)',  # I SA/Gl 81/25, II FSK 625/24
            r'([IVX]+\s+[A-Z]+\s+\d+[/]\d+)',  # I FSK 625/24
            r'([IVX]+[/\s]+[A-Z]+[/\s]*\w*\s+\d+[/]\d+)',  # I/SA/Wa 123/24
            r'([IVX]+\s+[A-Z]+/[A-Za-z]+\s+\d+[/]\d+)',  # I SA/Gl 123/24
        ]

        for pattern in signature_patterns:
            match = re.search(pattern, link_text, re.IGNORECASE)
            if match:
                signature = match.group(1).strip()
                # Clean up multiple spaces
                signature = re.sub(r'\s+', ' ', signature)
                return signature

        # If no signature found in link text, check surrounding text
        # Look at parent element or siblings for signature
        parent = link.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            for pattern in signature_patterns:
                match = re.search(pattern, parent_text, re.IGNORECASE)
                if match:
                    signature = match.group(1).strip()
                    signature = re.sub(r'\s+', ' ', signature)
                    return signature

        # Fallback: return the href path or link text
        return link_text if link_text else link.get('href', 'Unknown')

    def _parse_all_search_results(self, initial_content, initial_url, max_results):
        """Parse all pages of search results following pagination"""
        all_case_data = []
        current_content = initial_content
        page_num = 1

        while len(all_case_data) < max_results:
            self.logger.info(f"Parsing results page {page_num}")

            # Parse current page
            remaining_needed = max_results - len(all_case_data)
            page_cases = self._parse_search_results(current_content, remaining_needed)

            if not page_cases:
                self.logger.info(f"No more cases found on page {page_num}")
                break

            all_case_data.extend(page_cases)
            self.logger.info(f"Page {page_num}: found {len(page_cases)} cases, total: {len(all_case_data)}")

            # Check if we have enough results
            if len(all_case_data) >= max_results:
                self.logger.info(f"Reached maximum results limit: {max_results}")
                break

            # Look for next page link
            soup = BeautifulSoup(current_content, 'html.parser')
            next_link = self._find_next_page_link(soup)

            if not next_link:
                self.logger.info("No next page found, stopping pagination")
                break

            # Get next page
            try:
                time.sleep(self.delay)
                next_url = urljoin(self.base_url, next_link)
                self.logger.info(f"Fetching next page: {next_url}")
                
                response = self._get_with_retry(next_url, retries=3, backoff=1.6, timeout=(5, 30))
                response.raise_for_status()
                
                current_content = response.content
                page_num += 1

            except Exception as e:
                self.logger.exception(f"Error fetching next page: {e}")
                break

        return all_case_data[:max_results]  # Ensure we don't exceed limit

    def _find_next_page_link(self, soup):
        """Find the next page link in pagination"""
        # Look for common pagination patterns
        # CBOSA might use "następna", "dalej", ">" or similar
        next_patterns = [
            'następna',
            'dalej',
            'next',
            '&gt;',
            '>'
        ]
        
        # Search for links containing next page indicators
        links = soup.find_all('a', href=True)
        
        for link in links:
            link_text = link.get_text(strip=True).lower()
            href = link.get('href')
            
            # Check if this looks like a next page link
            for pattern in next_patterns:
                if pattern in link_text:
                    self.logger.info(f"Found next page link: {href} (text: '{link_text}')")
                    return href
        
        # Also look for numbered pagination (e.g., page 2, 3, etc.)
        for link in links:
            href = link.get('href')
            if href and ('page=' in href or 'strona=' in href):
                # Extract page number and see if it's next
                import re
                page_match = re.search(r'(page|strona)=(\d+)', href)
                if page_match:
                    page_num = int(page_match.group(2))
                    if page_num > 1:  # Assuming we start from page 1
                        self.logger.info(f"Found numbered next page: {href} (page {page_num})")
                        return href
        
        return None

    def download_case_rtf(self, case_url):
        """Download RTF content for a specific case"""
        try:
            time.sleep(self.delay)
            response = self._get_with_retry(case_url, retries=4, backoff=1.6, timeout=(5, 30))
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for RTF download link
            rtf_link = None
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href')
                link_text = link.get_text(strip=True).lower()
                
                # Look for RTF download indicators
                if ('rtf' in href.lower() or 
                    'rtf' in link_text or 
                    'pobierz' in link_text or
                    'download' in link_text):
                    rtf_link = href
                    break
            
            if not rtf_link:
                self.loggerwarning(f"No RTF download link found for {case_url}")
                return None
            
            # Download RTF content
            rtf_url = urljoin(self.base_url, rtf_link)
            time.sleep(self.delay)
            
            rtf_response = self._get_with_retry(rtf_url, retries=5, backoff=1.8, timeout=(5, 45))
            rtf_response.raise_for_status()
            
            return rtf_response.content
            
        except Exception as e:
            self.logger.exception(f"Error downloading RTF for {case_url}: {e}")
            return None

    def download_multiple_cases(self, case_data, progress_callback=None):
        """Download RTF content for multiple cases"""
        results = []
        total_cases = len(case_data)
        
        for i, case in enumerate(case_data, 1):
            case_url = case['url']
            signature = case['signature']
            
            self.logger.info(f"Downloading {i}/{total_cases}: {signature}")
            
            rtf_content = self.download_case_rtf(case_url)
            
            result = {
                'case_info': case,
                'content': rtf_content,
                'success': rtf_content is not None
            }
            
            results.append(result)
            
            if progress_callback:
                progress_callback(i, total_cases, result['success'])
        
        successful_downloads = sum(1 for r in results if r['success'])
        self.logger.info(f"Downloaded {successful_downloads}/{total_cases} cases successfully")
        
        return results
