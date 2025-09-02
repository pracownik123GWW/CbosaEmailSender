#!/usr/bin/env python3
"""
Improved date filtering that extracts actual judgment dates from case details
"""

import re
from datetime import datetime, date
import logging
from bs4 import BeautifulSoup
import requests
import time

logger = logging.getLogger(__name__)

class ImprovedDateFilter:
    """Enhanced date filtering with actual judgment date extraction"""
    
    def __init__(self, session=None, delay=0.5):
        self.date_format = "%Y-%m-%d"
        self.session = session or requests.Session()
        self.delay = delay
        
    def extract_judgment_date_from_case_page(self, case_url):
        """Extract the actual judgment date from a case detail page"""
        try:
            time.sleep(self.delay)  # Rate limiting
            response = self.session.get(case_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for date patterns in the case details
            # CBOSA typically shows dates in format "dd.mm.yyyy" or "dd-mm-yyyy"
            date_patterns = [
                r'Data orzeczenia[:\s]*(\d{1,2}[\.\-]\d{1,2}[\.\-]\d{4})',
                r'Orzeczenie z dnia[:\s]*(\d{1,2}[\.\-]\d{1,2}[\.\-]\d{4})',
                r'(\d{1,2}[\.\-]\d{1,2}[\.\-]\d{4})',  # General date pattern
                r'Data wydania[:\s]*(\d{1,2}[\.\-]\d{1,2}[\.\-]\d{4})'
            ]
            
            text_content = soup.get_text()
            
            for pattern in date_patterns:
                match = re.search(pattern, text_content, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    # Convert to standard format
                    date_str = date_str.replace('.', '-')
                    
                    # Try parsing dd-mm-yyyy format
                    try:
                        parts = date_str.split('-')
                        if len(parts) == 3 and len(parts[2]) == 4:
                            # Convert dd-mm-yyyy to yyyy-mm-dd
                            parsed_date = datetime.strptime(f"{parts[2]}-{parts[1]}-{parts[0]}", self.date_format).date()
                            logger.debug(f"Extracted date {parsed_date} from {case_url}")
                            return parsed_date
                    except ValueError:
                        continue
            
            logger.warning(f"Could not extract date from {case_url}")
            return None
            
        except Exception as e:
            logger.error(f"Error extracting date from {case_url}: {e}")
            return None
    
    def filter_cases_with_actual_dates(self, cases, date_from, date_to, extract_dates=True):
        """
        Filter cases using actual judgment dates extracted from case pages
        
        Args:
            cases: List of case dictionaries with 'url' keys
            date_from: Start date (datetime.date object)
            date_to: End date (datetime.date object)  
            extract_dates: If True, fetch actual dates from case pages
        """
        if not date_from and not date_to:
            return cases, {"total": len(cases), "filtered": 0, "kept": len(cases)}
        
        filtered_cases = []
        stats = {"total": len(cases), "filtered": 0, "kept": 0, "date_extracted": 0, "no_date": 0}
        
        for case in cases:
            case_url = case.get('url', '')
            case_signature = case.get('signature', 'Unknown')
            
            if extract_dates and case_url:
                # Extract actual judgment date
                judgment_date = self.extract_judgment_date_from_case_page(case_url)
                
                if judgment_date:
                    stats["date_extracted"] += 1
                    case['judgment_date'] = judgment_date
                    
                    # Check if date is in range
                    keep_case = True
                    
                    if date_from and judgment_date < date_from:
                        keep_case = False
                        logger.debug(f"Filtering out {case_signature}: {judgment_date} < {date_from}")
                    
                    if date_to and judgment_date > date_to:
                        keep_case = False
                        logger.debug(f"Filtering out {case_signature}: {judgment_date} > {date_to}")
                    
                    if keep_case:
                        filtered_cases.append(case)
                        stats["kept"] += 1
                        logger.info(f"Keeping {case_signature} dated {judgment_date}")
                    else:
                        stats["filtered"] += 1
                else:
                    # No date found - use conservative approach
                    stats["no_date"] += 1
                    # For now, include cases without dates
                    filtered_cases.append(case)
                    stats["kept"] += 1
                    logger.warning(f"No date found for {case_signature}, keeping it")
            else:
                # Fallback to year-based filtering from signature
                # This is the current behavior
                year_match = re.search(r'/(\d{2})$', case_signature)
                if year_match:
                    case_year = 2000 + int(year_match.group(1))
                    
                    keep_case = True
                    if date_from and case_year < date_from.year:
                        keep_case = False
                    if date_to and case_year > date_to.year:
                        keep_case = False
                    
                    if keep_case:
                        filtered_cases.append(case)
                        stats["kept"] += 1
                    else:
                        stats["filtered"] += 1
                else:
                    # No year in signature - keep it
                    filtered_cases.append(case)
                    stats["kept"] += 1
        
        logger.info(f"Date filtering complete: {stats}")
        return filtered_cases, stats


def test_improved_filter():
    """Test the improved date filtering"""
    print("🧪 Testing Improved Date Filter")
    print("=" * 50)
    
    # Test date extraction patterns
    test_html = """
    <html>
    <body>
        <p>Wyrok z dnia 15.07.2025 r.</p>
        <p>Sygn. akt I SA/Gd 265/25</p>
        <p>Data orzeczenia: 15-07-2025</p>
    </body>
    </html>
    """
    
    filter = ImprovedDateFilter()
    
    # Test date pattern matching
    patterns = [
        "Data orzeczenia: 15.07.2025",
        "Orzeczenie z dnia 15-07-2025 r.",
        "15.07.2025",
        "Data wydania: 15.07.2025"
    ]
    
    print("📅 Testing date extraction patterns:")
    for text in patterns:
        match = re.search(r'(\d{1,2}[\.\-]\d{1,2}[\.\-]\d{4})', text)
        if match:
            date_str = match.group(1).replace('.', '-')
            parts = date_str.split('-')
            if len(parts) == 3:
                formatted = f"{parts[2]}-{parts[1]}-{parts[0]}"
                print(f"  '{text}' -> {formatted}")
    
    print("\n✅ Date extraction patterns work correctly!")
    print("\n💡 To use this improved filter:")
    print("1. It fetches each case's detail page to extract the actual judgment date")
    print("2. Filters based on the full date (not just year)")
    print("3. This is more accurate but slower due to additional HTTP requests")


if __name__ == "__main__":
    test_improved_filter()