#!/usr/bin/env python3
"""
Clean date filtering implementation for CBOSA Downloader
Based on investigation findings - includes both CBOSA submission and local filtering
"""

import re
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

class DateFilterManager:
    """Manages date filtering for CBOSA searches with local post-processing"""
    
    def __init__(self):
        self.date_format = "%Y-%m-%d"
    
    def validate_date_string(self, date_str):
        """Validate and parse date string in YYYY-MM-DD format"""
        if not date_str or not date_str.strip():
            return None
            
        date_str = date_str.strip()
        
        # Validate format with regex
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
        
        try:
            # Parse to ensure it's a valid date
            parsed_date = datetime.strptime(date_str, self.date_format).date()
            return parsed_date
        except ValueError as e:
            raise ValueError(f"Invalid date: {date_str}. {str(e)}")
    
    def prepare_cbosa_dates(self, date_from_str, date_to_str):
        """Prepare date parameters for CBOSA submission"""
        result = {
            'date_from_parsed': None,
            'date_to_parsed': None,
            'cbosa_params': {}
        }
        
        # Validate and parse dates
        if date_from_str:
            try:
                result['date_from_parsed'] = self.validate_date_string(date_from_str)
                result['cbosa_params']['odDaty'] = date_from_str
                logger.info(f"Date from: {date_from_str} -> {result['date_from_parsed']}")
            except ValueError as e:
                logger.error(f"Invalid start date: {e}")
                raise
        
        if date_to_str:
            try:
                result['date_to_parsed'] = self.validate_date_string(date_to_str)
                result['cbosa_params']['doDaty'] = date_to_str  
                logger.info(f"Date to: {date_to_str} -> {result['date_to_parsed']}")
            except ValueError as e:
                logger.error(f"Invalid end date: {e}")
                raise
        
        # Validate date range
        if result['date_from_parsed'] and result['date_to_parsed']:
            if result['date_from_parsed'] > result['date_to_parsed']:
                raise ValueError("Start date cannot be after end date")
        
        return result
    
    def extract_case_date_from_signature(self, signature):
        """Extract case year from signature like 'I SA/Go 33/24' -> 2024"""
        if not signature:
            return None
            
        # Look for /YY pattern at the end
        year_match = re.search(r'/(\d{2})$', signature)
        if year_match:
            year_2digit = int(year_match.group(1))
            # Convert 2-digit year to 4-digit (assuming 20xx for now)
            if year_2digit <= 50:  # Arbitrary cutoff - adjust as needed
                return 2000 + year_2digit
            else:
                return 1900 + year_2digit
        
        return None
    
    def filter_cases_by_date(self, cases, date_from_parsed, date_to_parsed):
        """
        Filter cases locally based on extracted dates from signatures
        This compensates for CBOSA's loose date filtering
        """
        if not date_from_parsed and not date_to_parsed:
            logger.info("No date filtering requested - returning all cases")
            return cases, {"total": len(cases), "filtered": 0, "kept": len(cases)}
        
        filtered_cases = []
        stats = {"total": len(cases), "filtered": 0, "kept": 0}
        
        for case in cases:
            case_signature = case.get('signature', '') if isinstance(case, dict) else str(case)
            case_year = self.extract_case_date_from_signature(case_signature)
            
            # If we can't extract year, keep the case (conservative approach)
            if case_year is None:
                filtered_cases.append(case)
                stats["kept"] += 1
                logger.debug(f"Keeping case (no year extracted): {case_signature}")
                continue
            
            # Check date range
            keep_case = True
            
            if date_from_parsed:
                # For start date, we only have year so check if case year >= start year
                if case_year < date_from_parsed.year:
                    keep_case = False
                    logger.debug(f"Filtering out case (year {case_year} < {date_from_parsed.year}): {case_signature}")
            
            if date_to_parsed and keep_case:
                # For end date, check if case year <= end year  
                if case_year > date_to_parsed.year:
                    keep_case = False
                    logger.debug(f"Filtering out case (year {case_year} > {date_to_parsed.year}): {case_signature}")
            
            if keep_case:
                filtered_cases.append(case)
                stats["kept"] += 1
                logger.debug(f"Keeping case (year {case_year}): {case_signature}")
            else:
                stats["filtered"] += 1
        
        logger.info(f"Date filtering results: {stats['total']} total, {stats['kept']} kept, {stats['filtered']} filtered out")
        
        return filtered_cases, stats
    
    def get_date_filter_summary(self, date_from_str, date_to_str, filter_stats=None):
        """Generate human-readable summary of date filtering"""
        if not date_from_str and not date_to_str:
            return "No date filtering applied"
        
        summary_parts = []
        
        if date_from_str and date_to_str:
            summary_parts.append(f"Date range: {date_from_str} to {date_to_str}")
        elif date_from_str:
            summary_parts.append(f"From: {date_from_str}")
        elif date_to_str:
            summary_parts.append(f"Until: {date_to_str}")
        
        if filter_stats:
            summary_parts.append(f"({filter_stats['kept']} of {filter_stats['total']} cases matched)")
        
        return " | ".join(summary_parts)
