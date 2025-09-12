import sys
import json
import logging
import base64
from typing import List, Dict, Any

# Upewnij się, że importy wskazują na poprawne moduły
from cbosa_scraper.cbosa_scraper import CBOSAScraper
from cbosa_scraper.ai_judgment_analyzer import JudgmentAnalyzer
from cbosa_scraper.attachments import EmailAttachmentBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def scrape_cbosa_cases(search_params: Dict[str, Any], max_results: int = 50) -> List[Dict[str, Any]]:
    """Scrape CBOSA for cases based on search parameters"""
    try:
        logger.info(f"Starting CBOSA scraping with max_results={max_results}")
        scraper = CBOSAScraper(delay_between_requests=0.5)
        case_data = scraper.search_cases(search_params, max_results=max_results)

        if not case_data:
            logger.warning("No cases found")
            return []

        logger.info(f"Found {len(case_data)} cases, downloading RTF content...")
        download_results = scraper.download_multiple_cases(case_data)
        successful_downloads = [r for r in download_results if r.get('success')]
        logger.info(f"Successfully downloaded {len(successful_downloads)} RTF files")
        return successful_downloads

    except Exception as e:
        logger.exception(f"Error in CBOSA scraping: {e}")
        raise

def analyze_cases_with_ai(cases_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze downloaded cases with AI"""
    try:
        logger.info(f"Starting AI analysis of {len(cases_data)} cases")

        analyzer = JudgmentAnalyzer()

        # Prepare judgments for analysis
        judgments = []
        for case_data in cases_data:
            content = case_data.get('content')
            if content:
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='ignore')
                judgments.append({
                    'content': content,
                    'case_info': case_data.get('case_info', {})
                })

        # Analyze all judgments
        analysis_results = analyzer.analyze_multiple_judgments(judgments)

        # Calculate statistics (alias/uwspólnij z Twoją klasą)
        # Jeśli masz get_analysis_statistics, możesz użyć jej wprost:
        if hasattr(analyzer, "calculate_analysis_stats"):
            stats = analyzer.calculate_analysis_stats(analysis_results)
        else:
            stats = analyzer.get_analysis_statistics(analysis_results)

        successful_analyses = [r for r in analysis_results if r.get('success')]
        logger.info(f"Analysis complete: {len(successful_analyses)} successful analyses")

        return {
            'analyses': successful_analyses,
            'stats': stats,
            'all_results': analysis_results
        }

    except Exception as e:
        logger.exception(f"Error in AI analysis: {e}")
        raise

def build_attachments(analysis_data: Dict[str, Any], search_params: Dict[str, Any], successful_downloads: List[Dict[str, Any]], output_dir: str = "./out") -> Dict[str, Any]:
    """
    Build DOCX + TXT(stats) + ZIP attachments and return them as base64 for Node.
    """
    builder = EmailAttachmentBuilder(output_dir=output_dir)
    attachments = builder.build_all(
        analyses=analysis_data['analyses'],
        search_params=search_params,
        stats=analysis_data['stats'],
        successful_downloads=successful_downloads
    )

    # attachments: List[Tuple[filename, bytes, mime]]
    encoded = []
    for filename, data, mime in attachments:
        encoded.append({
            "filename": filename,
            "mime": mime,
            "b64": base64.b64encode(data).decode("ascii")
        })
    return {
        "attachments": encoded,
        # krótki mail body do użycia w kliencie (opcjonalny)
        "html_body": f"<p>W załączniku znajduje się biuletyn DOCX oraz statystyki TXT. "
                     f"Liczba orzeczeń: {len(analysis_data.get('analyses', []))}.</p>"
    }

def main():
    """Main entry point for bot runner"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command specified"}))
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == 'scrape':
            # Args: search_params (json), max_results (int)
            if len(sys.argv) < 4:
                raise ValueError("Missing arguments for scrape command")
            search_params = json.loads(sys.argv[2])
            max_results = int(sys.argv[3])
            result = scrape_cbosa_cases(search_params, max_results)
            print(json.dumps(result, default=str))

        elif command == 'analyze':
            # Args: cases_data (json)
            if len(sys.argv) < 3:
                raise ValueError("Missing arguments for analyze command")
            cases_data = json.loads(sys.argv[2])
            result = analyze_cases_with_ai(cases_data)
            print(json.dumps(result, default=str))

        elif command == 'newsletter':
            # Args: analysis_data (json), search_params (json), downloads (json), [output_dir]
            if len(sys.argv) < 5:
                raise ValueError("Missing arguments for newsletter command")
            analysis_data = json.loads(sys.argv[2])
            search_params = json.loads(sys.argv[3])
            successful_downloads = json.loads(sys.argv[4])
            output_dir = sys.argv[5] if len(sys.argv) >= 6 else "./out"

            result = build_attachments(
                analysis_data=analysis_data,
                search_params=search_params,
                successful_downloads=successful_downloads,
                output_dir=output_dir
            )
            print(json.dumps(result, ensure_ascii=False))

        else:
            raise ValueError(f"Unknown command: {command}")

    except Exception as e:
        logger.exception(f"Error in bot runner: {e}")
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
