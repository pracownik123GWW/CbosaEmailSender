from http.client import RemoteDisconnected
import random
import requests
from bs4 import BeautifulSoup
import time
import os
import logging
from urllib.parse import urljoin, urlparse
import re
from date_filter_manager import DateFilterManager
import json

logger = logging.getLogger(__name__)


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

    def search_cases(self, search_params, max_results=100):
        """
        Search for cases using the provided parameters
        Returns list of case URLs
        """
        try:
            logger.info(
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
                    logger.info(
                        f"Date filtering enabled: {self.date_filter.get_date_filter_summary(date_from_str, date_to_str)}"
                    )
                except ValueError as e:
                    logger.error(f"Date validation error: {e}")
                    raise

            # First, get the search form to understand its structure
            response = self.session.get(self.search_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Prepare form data based on the original form structure
            form_data = self._prepare_form_data(search_params, soup)

            # Add date parameters to CBOSA form if provided
            if date_filter_info and date_filter_info['cbosa_params']:
                form_data.update(date_filter_info['cbosa_params'])
                logger.info(
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

            logger.info(
                f"Found {len(case_data)} cases from CBOSA (before local filtering)"
            )

            # Skip local date filtering - CBOSA handles date filtering correctly
            # The signature year (e.g., /24) doesn't necessarily match the judgment date
            logger.info(
                f"Using CBOSA's date filtering results without additional local filtering"
            )

            logger.info(
                f"Final result: {len(case_data)} cases after all filtering")
            return case_data

        except Exception as e:
            logger.error(f"Error in search_cases: {str(e)}")
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
        logger.info("Form data being sent to CBOSA:")
        for key, value in form_data.items():
            logger.info(f"  {key}: {value}")

        # Special debug for judgment type issue
        if 'rodzaj' in form_data:
            logger.info(
                f">>> JUDGMENT TYPE DEBUG: rodzaj = '{form_data['rodzaj']}'")
        else:
            logger.info(
                ">>> JUDGMENT TYPE DEBUG: 'rodzaj' field is MISSING from form data!"
            )
            logger.info(
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
                        logger.info(
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
                    logger.info(
                        f"🔴 Skipping related case: {signature} (parent classes: {parent_classes})"
                    )
                else:
                    logger.debug(
                        f"⚪ Unknown link type: {href} (parent classes: {parent_classes})"
                    )

        # If no primary results found, look for alternative patterns but still respect class filtering
        if not case_data:
            logger.warning(
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
                            logger.info(
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
        ]

        for pattern in signature_patterns:
            match = re.search(pattern, link_text, re.IGNORECASE)
            if match:
                signature = match.group(1)
                # Clean up the signature
                signature = re.sub(r'\s+', ' ', signature).strip()
                logger.info(f"Found case signature in link text: {signature}")
                return signature

        # If not found in link text, look in parent elements (table cells, etc.)
        parent = link.parent
        if parent:
            parent_text = parent.get_text(strip=True)
            for pattern in signature_patterns:
                match = re.search(pattern, parent_text, re.IGNORECASE)
                if match:
                    signature = match.group(1)
                    signature = re.sub(r'\s+', ' ', signature).strip()
                    logger.info(
                        f"Found case signature in parent element: {signature}")
                    return signature

        # Look in surrounding table row or div
        row = link.find_parent(['tr', 'div', 'li'])
        if row:
            row_text = row.get_text(strip=True)
            for pattern in signature_patterns:
                match = re.search(pattern, row_text, re.IGNORECASE)
                if match:
                    signature = match.group(1)
                    signature = re.sub(r'\s+', ' ', signature).strip()
                    logger.info(f"Found case signature in row: {signature}")
                    return signature

        # As a last resort, extract from href if it contains meaningful text
        href = link.get('href', '')
        if href:
            for pattern in signature_patterns:
                match = re.search(pattern, href, re.IGNORECASE)
                if match:
                    signature = match.group(1)
                    signature = re.sub(r'\s+', ' ', signature).strip()
                    logger.info(f"Found case signature in href: {signature}")
                    return signature

        logger.warning(
            f"No case signature found for link: {link_text[:50]}...")
        return None

    def _parse_all_search_results(self, content, current_url, max_results):
        """Parse search results across all pages using pagination"""
        all_case_data = []
        page_num = 1
        max_pages = 20  # Safety limit to prevent infinite loops
        consecutive_errors = 0

        while len(all_case_data) < max_results and page_num <= max_pages:
            logger.info(f"Parsing page {page_num} of search results...")

            # Get cases from current page
            page_cases = self._parse_search_results(
                content, max_results - len(all_case_data))
            all_case_data.extend(page_cases)

            logger.info(
                f"Found {len(page_cases)} cases on page {page_num}, total: {len(all_case_data)}"
            )

            # If we have enough results or no cases found on this page, stop
            if len(all_case_data) >= max_results or len(page_cases) == 0:
                break

            # Look for next page link
            next_url = self._find_next_page_url(content, current_url)
            if not next_url:
                logger.info("No more pages found")
                break

            # Get the next page with better error handling
            try:
                logger.info(f"Fetching next page: {next_url}")
                time.sleep(self.delay *
                           2)  # Slower pagination to be more polite
                response = self._get_with_retry(next_url, retries=3, backoff=1.6, timeout=(5, 30))
                response.raise_for_status()
                content = response.content
                current_url = response.url
                page_num += 1
                consecutive_errors = 0  # Reset error counter on success

                # Add extra delay every few pages to be respectful
                if page_num % 5 == 0:
                    logger.info(f"Pausing briefly after {page_num} pages...")
                    time.sleep(2)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error fetching page {page_num + 1}: {str(e)}")

                # If we have multiple consecutive errors, stop
                if consecutive_errors >= 3:
                    logger.info(
                        f"Multiple consecutive errors, stopping pagination")
                    break

                # Otherwise, return what we have so far
                logger.info(
                    f"Stopping pagination at page {page_num}, returning {len(all_case_data)} cases found so far"
                )
                break

        if page_num > max_pages:
            logger.info(
                f"Reached maximum page limit ({max_pages}), returning {len(all_case_data)} cases"
            )

        return all_case_data[:max_results]

    def _find_next_page_url(self, content, current_url):
        """Find the URL for the next page of results"""
        from urllib.parse import urljoin

        soup = BeautifulSoup(content, 'html.parser')

        # Look for "następna »" (next) link
        next_links = soup.find_all('a', href=True)
        for link in next_links:
            link_text = link.get_text(strip=True)
            if 'następna' in link_text.lower() or '»' in link_text:
                href = link.get('href')
                if href:
                    # Convert relative URL to absolute
                    next_url = urljoin(current_url, href)
                    return next_url

        # If no "nastepna »" link found, end search
        logger.info("No 'następna »' link found, ending search")

        return None
    
    def _get_with_retry(self, url, *, retries=4, backoff=1.6, timeout=(5, 40)):
        """
        GET z retry dla błędów sieciowych/5xx/429. Zwraca requests.Response
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
                # exponential backoff + jitter; przy 429 jeszcze dłużej
                base_sleep = (backoff ** (attempt - 1))
                jitter = random.uniform(0, 0.4)
                extra = 1.5 if isinstance(e, requests.HTTPError) and getattr(e, "response", None) and e.response is not None and e.response.status_code == 429 else 0.0
                time.sleep(base_sleep + jitter + extra)
        raise last_err
    
    def download_case_pdf(self, case_data, download_dir):
        """
        Download PDF for a specific case
        Args:
            case_data: Can be either a URL string (old format) or dict with 'url' and 'signature'
            download_dir: Directory to save the file
        Returns the path to the downloaded PDF file
        """
        try:
            # Handle both old format (string URL) and new format (dict with URL and signature)
            if isinstance(case_data, str):
                case_url = case_data
                provided_signature = None
            else:
                case_url = case_data['url']
                provided_signature = case_data.get('signature')

            logger.info(f"Downloading PDF for case: {case_url}")
            if provided_signature:
                logger.info(f"Using provided signature: {provided_signature}")

            # First, get the case page
            time.sleep(self.delay)
            response = self._get_with_retry(case_url, retries=4, backoff=1.6, timeout=(5, 30))

            # Look for PDF download link
            pdf_url = self._find_pdf_url(response.content, case_url)

            if not pdf_url:
                logger.warning(f"No PDF URL found for case: {case_url}")
                return None

            # Download the document
            time.sleep(self.delay)
            doc_response = self._get_with_retry(pdf_url, retries=5, backoff=1.8, timeout=(5, 45))

            # Check if it's actually a PDF or RTF
            content = doc_response.content
            case_id = self._extract_case_id(case_url)

            # Use provided signature first, then try to extract from content
            case_signature = provided_signature
            if not case_signature and content.startswith(b'{\\rtf'):
                try:
                    case_signature = self._extract_case_signature_from_rtf(
                        content)
                except:
                    pass

            # Create filename using signature if available, otherwise use case_id
            if case_signature:
                # Clean filename by removing illegal characters
                safe_signature = re.sub(r'[<>:"/\\|?*]', '_', case_signature)
                safe_signature = safe_signature.replace(' ', '_')
                logger.info(
                    f"Using case signature for filename: {case_signature} -> {safe_signature}"
                )
            else:
                safe_signature = case_id
                logger.info(f"No signature found, using case ID: {case_id}")

            # Determine file type by content
            if content.startswith(b'%PDF'):
                # It's a real PDF
                filename = f"{safe_signature}.pdf"
                filepath = os.path.join(download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(content)
            elif content.startswith(b'{\\rtf'):
                # It's RTF format - save as .rtf file
                filename = f"{safe_signature}.rtf"
                filepath = os.path.join(download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(content)
                logger.info(f"Document is RTF format, saved as: {filename}")
            else:
                # Unknown format, save as .txt and log first 200 chars
                filename = f"{safe_signature}.txt"
                filepath = os.path.join(download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(content)
                logger.warning(
                    f"Unknown document format for {case_id}, first 200 chars: {content[:200]}"
                )

            logger.info(f"Successfully downloaded: {filename}")
            return filepath

        except Exception as e:
            logger.error(f"Error downloading PDF for {case_url}: {str(e)}")
            return None

    def _find_pdf_url(self, content, case_url):
        """Find PDF download URL on the case page"""
        soup = BeautifulSoup(content, 'html.parser')

        # First, look for actual PDF links (direct downloads)
        links = soup.find_all('a', href=True)

        for link in links:
            href = link.get('href')
            if href and not href.startswith('javascript:'):
                # Check if this is a direct PDF link
                if href.endswith('.pdf'):
                    return urljoin(self.base_url, href)

                # Check for PDF-related paths that don't have javascript
                if any(pattern in href.lower()
                       for pattern in ['/pdf/', 'pdf.do', 'doc.pdf']):
                    return urljoin(self.base_url, href)

        # If no direct PDF links found, construct PDF URL based on case ID
        # CBOSA typically allows PDF access via /doc/ID.pdf pattern
        case_id = self._extract_case_id(case_url)
        if case_id:
            potential_pdf_url = f"{self.base_url}/doc/{case_id}.pdf"
            return potential_pdf_url

        return None

    def _extract_case_id(self, case_url):
        """Extract case ID from the URL"""
        # Try to extract ID from URL patterns (including alphanumeric IDs)
        patterns = [
            r'/doc/([A-Za-z0-9]+)/?$',  # Alphanumeric doc ID (most common for CBOSA)
            r'/([A-Za-z0-9]+)/?$',  # Alphanumeric ID at the end
            r'id=([A-Za-z0-9]+)',  # ID parameter
            r'case_([A-Za-z0-9]+)'  # Case ID
        ]

        for pattern in patterns:
            match = re.search(pattern, case_url)
            if match:
                return match.group(1)

        # Fallback: extract last path component
        url_parts = case_url.rstrip('/').split('/')
        if url_parts:
            return url_parts[-1]

        # Final fallback: use timestamp
        return str(int(time.time()))

    def _extract_case_signature_from_rtf(self, rtf_content):
        """Extract case signature from RTF content"""
        import re
        from striprtf.striprtf import rtf_to_text

        try:
            # Convert RTF to plain text
            if isinstance(rtf_content, bytes):
                rtf_content = rtf_content.decode('utf-8', errors='ignore')

            text = rtf_to_text(rtf_content)

            # Look for typical Polish court case signatures
            patterns = [
                r'([IVX]+\s+[A-Z]{2,4}\s+\d+[/]\d+)',  # I FSK 625/24, II OSK 456/24
                r'([IVX]+\s+[A-Z]+[/\s]*[A-Za-z]*\s+\d+[/]\d+)',  # I SA/Po 188/25
                r'([IVX]+\s+S[A-Z]+[/\s]*\w+\s+\d+[/]\d+)',  # I SA/Wa 123/24  
                r'(Sygn[.\s]*akt[:\s]*[IVX]+\s+[A-Z/\w\s]+\d+[/]\d+)',  # Sygn. akt: pattern
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Return the first match, cleaned up
                    signature = matches[0].strip()
                    signature = re.sub(r'\s+', ' ',
                                       signature)  # Normalize spaces
                    signature = signature.replace('Sygn. akt:', '').strip()
                    logger.info(f"Extracted case signature: {signature}")
                    return signature

            logger.warning("No case signature found in RTF content")
            return None

        except Exception as e:
            logger.error(f"Error extracting case signature: {e}")
            return None

    def test_download(self, num_cases=3):
        """
        Test method to download a small number of cases
        Used for unit testing
        """
        try:
            # Simple search for recent cases
            search_params = {
                'keywords': '',
                'date_from': '2024-01-01',
                'with_justification': 'Tak'
            }

            case_urls = self.search_cases(search_params, max_results=num_cases)

            if not case_urls:
                logger.warning("No test cases found")
                return []

            # Create temp directory
            import tempfile
            temp_dir = tempfile.mkdtemp()
            downloaded_files = []

            for case_url in case_urls[:num_cases]:
                pdf_path = self.download_case_pdf(case_url, temp_dir)
                if pdf_path:
                    downloaded_files.append(pdf_path)

            return downloaded_files

        except Exception as e:
            logger.error(f"Error in test_download: {str(e)}")
            return []
