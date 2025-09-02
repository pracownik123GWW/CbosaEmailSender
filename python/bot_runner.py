#!/usr/bin/env python3
"""
Main bot runner script that handles CBOSA scraping, AI analysis, and newsletter generation
Called from Node.js via child process
"""

import sys
import json
import logging
from cbosa_scraper import CBOSAScraper
from ai_judgment_analyzer import JudgmentAnalyzer
from newsletter_generator import NewsletterGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def scrape_cbosa_cases(search_params, max_results=50):
    """Scrape CBOSA for cases based on search parameters"""
    try:
        logger.info(f"Starting CBOSA scraping with max_results={max_results}")
        
        scraper = CBOSAScraper(delay_between_requests=0.5)
        case_data = scraper.search_cases(search_params, max_results=max_results)
        
        if not case_data:
            logger.warning("No cases found")
            return []
        
        logger.info(f"Found {len(case_data)} cases, downloading RTF content...")
        
        # Download RTF content for all cases
        download_results = scraper.download_multiple_cases(case_data)
        
        # Filter successful downloads
        successful_downloads = [r for r in download_results if r['success']]
        
        logger.info(f"Successfully downloaded {len(successful_downloads)} RTF files")
        
        return successful_downloads
        
    except Exception as e:
        logger.error(f"Error in CBOSA scraping: {e}")
        raise

def analyze_cases_with_ai(cases_data):
    """Analyze downloaded cases with AI"""
    try:
        logger.info(f"Starting AI analysis of {len(cases_data)} cases")
        
        analyzer = JudgmentAnalyzer()
        
        # Prepare judgments for analysis
        judgments = []
        for case_data in cases_data:
            if case_data['content']:
                judgments.append({
                    'content': case_data['content'].decode('utf-8', errors='ignore') if isinstance(case_data['content'], bytes) else case_data['content'],
                    'case_info': case_data['case_info']
                })
        
        # Analyze all judgments
        analysis_results = analyzer.analyze_multiple_judgments(judgments)
        
        # Calculate statistics
        stats = analyzer.calculate_analysis_stats(analysis_results)
        
        # Filter successful analyses
        successful_analyses = [r for r in analysis_results if r['success']]
        
        logger.info(f"Analysis complete: {len(successful_analyses)} successful analyses")
        
        return {
            'analyses': successful_analyses,
            'stats': stats,
            'all_results': analysis_results
        }
        
    except Exception as e:
        logger.error(f"Error in AI analysis: {e}")
        raise

def generate_newsletter_html(analysis_data):
    """Generate HTML newsletter from analysis data"""
    try:
        analyses = analysis_data['analyses']
        stats = analysis_data['stats']
        
        logger.info(f"Generating newsletter with {len(analyses)} analyses")
        
        generator = NewsletterGenerator()
        html_content = generator.generate_newsletter(
            analyses=analyses,
            search_params={},  # Not needed for display
            stats=stats
        )
        
        logger.info("Newsletter HTML generated successfully")
        return html_content
        
    except Exception as e:
        logger.error(f"Error generating newsletter: {e}")
        raise

def main():
    """Main entry point for bot runner"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command specified"}))
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == 'scrape':
            # Scrape CBOSA cases
            if len(sys.argv) < 4:
                raise ValueError("Missing arguments for scrape command")
            
            search_params = json.loads(sys.argv[2])
            max_results = int(sys.argv[3])
            
            result = scrape_cbosa_cases(search_params, max_results)
            print(json.dumps(result, default=str))
            
        elif command == 'analyze':
            # Analyze cases with AI
            if len(sys.argv) < 3:
                raise ValueError("Missing arguments for analyze command")
            
            cases_data = json.loads(sys.argv[2])
            result = analyze_cases_with_ai(cases_data)
            print(json.dumps(result, default=str))
            
        elif command == 'newsletter':
            # Generate newsletter
            if len(sys.argv) < 3:
                raise ValueError("Missing arguments for newsletter command")
            
            analysis_data = json.loads(sys.argv[2])
            result = generate_newsletter_html(analysis_data)
            print(result)  # Return raw HTML
            
        else:
            raise ValueError(f"Unknown command: {command}")
            
    except Exception as e:
        logger.error(f"Error in bot runner: {e}")
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
