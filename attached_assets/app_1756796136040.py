import os
import logging
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from cbosa_scraper import CBOSAScraper
from ai_judgment_analyzer import JudgmentAnalyzer
from newsletter_generator import NewsletterGenerator
import tempfile
import zipfile
from datetime import datetime
import threading
import uuid
import time
from threading import Lock
import json
import unicodedata
import re

MAX_SEARCH_RESULTS = 400  # Limit to prevent excessive downloads
UNLIMITED_SEARCH = 10**9

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET",
                                "dev-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Global dictionary to track large downloads
large_downloads = {}
downloads_lock = Lock()

# Load judges by court data
JUDGES_BY_COURT = {}
try:
    judges_path = os.path.join(app.root_path, "static", "data", "judges_by_court.json")
    with open(judges_path, "r", encoding="utf-8") as f:
        JUDGES_BY_COURT = json.load(f)
    logger.info(f"Loaded judges index: courts={len(JUDGES_BY_COURT)}")
except Exception as e:
    logger.error(f"Could not load judges JSON: {e}")
    JUDGES_BY_COURT = {}

def _norm(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _is_garbage(display: str) -> bool:
    if not display: 
        return True
    bad = ["uściślij warunek", "..."]
    d = display.strip().lower()
    if any(b in d for b in bad): 
        return True
    if d[0] in ".0123456789": 
        return True
    return False

def generate_newsletter_html(analyses, search_params, stats=None):
    """Generate HTML newsletter with AI analyses"""
    current_date = datetime.now().strftime('%d.%m.%Y')

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Biuletyn Analityczny CBOSA</title>
    <link href="https://cdn.replit.com/agent/bootstrap-agent-dark-theme.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #1a1a1a; color: #ffffff; }}
        .newsletter-header {{ background: linear-gradient(135deg, #2c3e50, #3498db); padding: 2rem; margin-bottom: 2rem; }}
        .analysis-card {{ background-color: #2d2d2d; border-left: 4px solid #3498db; margin-bottom: 2rem; padding: 1.5rem; }}
        .analysis-title {{ color: #3498db; font-size: 1.2rem; font-weight: bold; margin-bottom: 1rem; }}
        .analysis-content {{ line-height: 1.6; white-space: pre-line; }}
        .meta-info {{ color: #888; font-size: 0.9rem; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="newsletter-header text-center">
            <h1><i class="fas fa-gavel me-2"></i>Biuletyn Analityczny CBOSA</h1>
            <p class="lead">Analiza Orzeczeń Sądów Administracyjnych</p>
            <p><strong>Data:</strong> {current_date} | <strong>Liczba orzeczeń:</strong> {len(analyses)}</p>
        </div>
        
        <div class="row">
            <div class="col-12">
                <div class="alert alert-info">
                    <i class="fas fa-robot me-2"></i>
                    <strong>Automatyczna analiza AI:</strong> 
                    Ten biuletyn został wygenerowany automatycznie przy użyciu sztucznej inteligencji ChatGPT. 
                    Analiza ma charakter pomocniczy i nie zastępuje profesjonalnej interpretacji prawnej.
                </div>
            </div>
        </div>
"""

    # Add each analysis
    for i, analysis in enumerate(analyses, 1):
        html_content += f"""
        <div class="analysis-card">
            <div class="analysis-title">
                <i class="fas fa-file-alt me-2"></i>Orzeczenie {i}: {analysis['filename']}
            </div>
            <div class="meta-info">
                <i class="fas fa-link me-1"></i>Źródło: {analysis['case_url'][:50]}...
            </div>
            <div class="analysis-content">
{analysis['analysis']}
            </div>
        </div>
        """

    html_content += """
        <div class="mt-5 pt-4 border-top text-center">
            <p class="text-muted">
                <i class="fas fa-info-circle me-1"></i>
                Biuletyn wygenerowany przez CBOSA Downloader z analizą AI
            </p>
        </div>
    </div>
</body>
</html>
"""

    return html_content


def generate_analysis_summary(stats, analysis_results):
    """Generate text summary of AI analysis statistics"""
    current_date = datetime.now().strftime('%d.%m.%Y %H:%M')

    failed_analyses = [r for r in analysis_results if not r['success']]

    summary = f"""PODSUMOWANIE ANALIZY AI - CBOSA DOWNLOADER
Wygenerowano: {current_date}

=== STATYSTYKI OGÓLNE ===
Łączna liczba orzeczeń: {stats['total_analyses']}
Udane analizy: {stats['successful_analyses']}
Nieudane analizy: {stats['failed_analyses']}
Współczynnik sukcesu: {stats['success_rate']:.1f}%

=== KOSZTY I ZUŻYCIE ===
Łączne tokeny użyte: {stats['total_tokens_used']:,}
Średnia tokenów na analizę: {stats['average_tokens_per_analysis']}
Szacowany koszt USD: ${stats['estimated_cost_usd']}
Szacowany koszt PLN: {stats['estimated_cost_pln']} zł

=== SZCZEGÓŁY BŁĘDÓW ===
"""

    if failed_analyses:
        summary += f"Liczba błędów: {len(failed_analyses)}\n\n"
        for i, failed in enumerate(failed_analyses[:5],
                                   1):  # Show first 5 errors
            case_info = failed.get('case_info', {})
            filename = case_info.get('filename', 'Unknown')
            error = failed.get('error', 'Unknown error')
            summary += f"{i}. {filename}: {error}\n"

        if len(failed_analyses) > 5:
            summary += f"... i {len(failed_analyses) - 5} więcej błędów\n"
    else:
        summary += "Brak błędów - wszystkie analizy zakończone sukcesem!\n"

    summary += f"""
=== INFORMACJE TECHNICZNE ===
Model AI: GPT-4o (OpenAI)
Język analizy: Polski
Format wyjściowy: HTML Newsletter
Data generowania: {current_date}

Analiza wykonana przez CBOSA Downloader z integracją ChatGPT AI.
"""

    return summary


@app.route('/')
def index():
    """Main search form page"""
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    """Handle search form submission and process download"""
    try:
        # Extract all form parameters
        search_params = {
            'keywords':
            request.form.get('keywords', ''),
            'keywords_location':
            request.form.get('keywords_location', 'gdziekolwiek'),
            'with_inflection':
            request.form.get('with_inflection', ''),
            'signature':
            request.form.get('signature', ''),
            'court':
            request.form.get('court', ''),
            'judgment_type':
            request.form.get('judgment_type', ''),
            'case_symbol':
            request.form.get('case_symbol', ''),
            'date_from':
            request.form.get('date_from', ''),
            'date_to':
            request.form.get('date_to', ''),
            'judge':
            request.form.get('judge', ''),
            'judge_function':
            request.form.get('judge_function', ''),
            'final_judgment':
            request.form.get('final_judgment', ''),
            'ending_judgment':
            request.form.get('ending_judgment', ''),
            'with_thesis':
            request.form.get('with_thesis', ''),
            'with_justification':
            request.form.get('with_justification', ''),
            'with_dissenting':
            request.form.get('with_dissenting', ''),
            'organ_type':
            request.form.get('organ_type', ''),
            'thematic_tags':
            request.form.get('thematic_tags', ''),
            'legal_act':
            request.form.get('legal_act', ''),
            'legal_provision':
            request.form.get('legal_provision', ''),
            'published':
            request.form.get('published', ''),
            'publication_details':
            request.form.get('publication_details', ''),
            'with_commentary':
            request.form.get('with_commentary', ''),
            'commentary_details':
            request.form.get('commentary_details', '')
        }

        # Debug: Log what we received from the form
        logger.info("=== FORM PARAMETERS RECEIVED ===")
        for key, value in search_params.items():
            if value:  # Only log non-empty values
                logger.info(f"  {key}: {value}")
        logger.info("======================================")

        # Get AI analysis parameters
        enable_ai_analysis = request.form.get('enable_ai_analysis') == '1'
        ai_email = request.form.get('ai_email', '').strip()
        ai_format = request.form.get('ai_format', 'docx')

        # Get max_results from form, default to 100
        use_limit = request.form.get('use_limit') == 'on'
        limit_count_raw = request.form.get('limit_count', '').strip()
        
        max_results = None
        if use_limit:
            n = None
            try:
                n = int(limit_count_raw) if limit_count_raw else None
            except ValueError as e:
                logger.warning(f"Invalid limit_count value: {limit_count_raw} - {e}")
            
            if n is None:
                n = 0
            if n < 1:
                n = 1
            if n > MAX_SEARCH_RESULTS:
                n = MAX_SEARCH_RESULTS
            
            max_results = n
        else:
            max_results = UNLIMITED_SEARCH

        # First, do a quick search to see how many cases we'll get
        scraper = CBOSAScraper(delay_between_requests=0.5)
        case_data = scraper.search_cases(search_params,
                                         max_results=max_results)

        if not case_data:
            return render_template(
                'index.html', error='No cases found for your search criteria.')

        # All downloads now use background processing to prevent timeouts
        ai_params = {
            'enable_ai_analysis': enable_ai_analysis,
            'ai_email': ai_email,
            'ai_format': ai_format
        }
        return process_download(case_data, search_params, ai_params)

    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
        return render_template('index.html',
                               error=f"Error processing search: {str(e)}")


def process_download(case_data, search_params, ai_params=None):
    """Handle all downloads with background processing to prevent timeouts"""
    # Generate unique download ID
    download_id = str(uuid.uuid4())
    session['download_id'] = download_id

    # Initialize progress tracking
    with downloads_lock:
        large_downloads[download_id] = {
            'status': 'starting',
            'progress': 0,
            'total': len(case_data),
            'current': 0,
            'succeeded': 0,
            'failed': 0,
            'failed_items': [],
            'message': f'Starting download of {len(case_data)} cases...',
            'zip_path': None,
            'error': None
        }

    # Start download process in background thread
    thread = threading.Thread(target=process_download_background,
                              args=(download_id, case_data, search_params,
                                    ai_params))
    thread.daemon = True
    thread.start()

    return redirect(url_for('large_download_status'))


def process_download_background(download_id,
                                case_data,
                                search_params,
                                ai_params=None):
    """Background process for all downloads"""
    try:
        scraper = CBOSAScraper(
            delay_between_requests=0.8)  # Slower for large downloads

        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        zip_filename = f"cbosa_large_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)

        # Update status
        with downloads_lock:
            large_downloads[download_id]['status'] = 'downloading'
            large_downloads[download_id][
                'message'] = 'Downloading court documents...'

        # Store RTF contents for AI analysis if requested
        rtf_contents = []

        # Download all documents
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, case in enumerate(case_data, 1):
                # Update progress
                with downloads_lock:
                    large_downloads[download_id]['current'] = i
                    large_downloads[download_id]['progress'] = int(
                        (i / len(case_data)) * 50)  # Use 50% for download
                    large_downloads[download_id][
                        'message'] = f'Downloading case {i} of {len(case_data)}...'

                logger.info(
                    f"Large download {download_id}: case {i} of {len(case_data)}"
                )
                doc_path = scraper.download_case_pdf(case, temp_dir)
                if doc_path and os.path.exists(doc_path):
                    zipf.write(doc_path, os.path.basename(doc_path))
                    with downloads_lock:
                        large_downloads[download_id]['succeeded'] += 1
                    
                    # Store RTF content for AI analysis
                    if ai_params and ai_params.get('enable_ai_analysis'):
                        try:
                            with open(doc_path, 'r', encoding='utf-8') as f:
                                rtf_content = f.read()

                                # Extract proper case signature for filename
                                case_signature = None
                                try:
                                    temp_analyzer = JudgmentAnalyzer()
                                    case_signature = temp_analyzer.extract_case_signature(
                                        rtf_content)
                                    if case_signature:
                                        # Use case signature as filename (clean for filesystem)
                                        clean_signature = case_signature.replace(
                                            '/', '_').replace(' ',
                                                              '_').replace(
                                                                  '\\', '_')
                                        proper_filename = f"{clean_signature}.rtf"
                                        logger.info(
                                            f"Extracted case signature: {case_signature} -> filename: {proper_filename}"
                                        )
                                    else:
                                        proper_filename = os.path.basename(
                                            doc_path)
                                        logger.warning(
                                            f"No case signature found, using: {proper_filename}"
                                        )
                                except Exception as e:
                                    logger.error(
                                        f"Error extracting case signature: {e}"
                                    )
                                    proper_filename = os.path.basename(
                                        doc_path)

                                rtf_contents.append({
                                    'content':
                                    rtf_content,
                                    'filename':
                                    proper_filename,
                                    'case_signature':
                                    case_signature or 'Unknown',
                                    'case_url':
                                    case.get('url', 'Unknown') if isinstance(
                                        case, dict) else str(case)
                                })
                        except Exception as e:
                            logger.warning(
                                f"Could not read RTF content for AI analysis: {e}"
                            )

                    os.remove(doc_path)
                else:
                    with downloads_lock:
                        large_downloads[download_id]['failed'] += 1
                        failed_desc = case.get('signature') if isinstance(case, dict) else str(case)
                        failed_url = case.get('url') if isinstance(case, dict) else str(case)
                        large_downloads[download_id]['failed_items'].append({
                            'signature': failed_desc or 'Unknown',
                            'url': failed_url or 'Unknown'
                        })

        # Process AI analysis if requested
        if ai_params and ai_params.get('enable_ai_analysis') and rtf_contents:
            try:
                # Update status for AI processing
                with downloads_lock:
                    large_downloads[download_id]['status'] = 'ai_processing'
                    large_downloads[download_id][
                        'message'] = 'Analyzing documents with AI...'

                # Initialize AI analyzer
                analyzer = JudgmentAnalyzer()

                # Test API connection first
                if not analyzer.validate_api_connection():
                    raise Exception(
                        "Cannot connect to OpenAI API. Please check your API key."
                    )

                # Prepare judgments for batch analysis
                judgments_for_analysis = []
                for rtf_data in rtf_contents:
                    judgments_for_analysis.append({
                        'content':
                        rtf_data['content'],
                        'metadata': {
                            'filename': rtf_data['filename'],
                            'case_url': rtf_data['case_url']
                        }
                    })

                # Define progress callback for AI analysis
                def ai_progress_callback(current, total, success):
                    ai_progress = 50 + int((current / total) * 50)
                    with downloads_lock:
                        large_downloads[download_id]['progress'] = ai_progress
                        large_downloads[download_id][
                            'message'] = f'AI analyzing case {current} of {total}...'
                    status = "✓" if success else "✗"
                    logger.info(
                        f"AI Progress: {status} {current}/{total} - {ai_progress}%"
                    )

                # Use enhanced batch analysis with retry logic
                analysis_results = analyzer.batch_analyze_with_limits(
                    judgments_for_analysis,
                    max_tokens_per_batch=
                    120000,  # Increased batch size for 5-8 rulings per batch
                    progress_callback=ai_progress_callback)

                # Extract successful analyses for newsletter
                analyses = []
                for result in analysis_results:
                    if result['success']:
                        metadata = result.get('case_info', {})
                        analyses.append({
                            'filename':
                            metadata.get('filename', 'Unknown'),
                            'analysis':
                            result['analysis'],
                            'case_url':
                            metadata.get('case_url', '')
                        })

                # Log analysis statistics
                stats = analyzer.get_analysis_statistics(analysis_results)
                logger.info(
                    f"AI Analysis Stats: {stats['successful_analyses']}/{stats['total_analyses']} successful, "
                    f"Cost: ~{stats['estimated_cost_pln']} PLN, Tokens: {stats['total_tokens_used']}"
                )

                # Generate newsletter report
                if analyses:
                    try:
                        # Initialize newsletter generator
                        newsletter_gen = NewsletterGenerator()

                        # Get format from AI parameters (default to RTF for Polish characters)
                        report_format = ai_params.get('ai_format', 'rtf')
                        if report_format == 'html':
                            report_format = 'rtf'  # Default to RTF for best Polish character support

                        # Generate newsletter in requested format
                        with downloads_lock:
                            large_downloads[download_id][
                                'message'] = f'Generating {report_format.upper()} newsletter...'

                        newsletter_path = newsletter_gen.generate_newsletter(
                            format_type=report_format,
                            analyses=analyses,
                            search_params=search_params,
                            stats=stats,
                            output_dir=temp_dir)

                        # Add newsletter to ZIP
                        with zipfile.ZipFile(zip_path, 'a') as zipf:
                            zipf.write(newsletter_path,
                                       os.path.basename(newsletter_path))

                        # Create summary statistics file
                        stats_content = generate_analysis_summary(
                            stats, analysis_results)
                        stats_path = os.path.join(temp_dir,
                                                  "AI_Analysis_Summary.txt")
                        with open(stats_path, 'w', encoding='utf-8') as f:
                            f.write(stats_content)

                        with zipfile.ZipFile(zip_path, 'a') as zipf:
                            zipf.write(stats_path, "AI_Analysis_Summary.txt")

                        with downloads_lock:
                            large_downloads[download_id][
                                'message'] = f'Successfully analyzed {len(analyses)}/{len(rtf_contents)} cases with AI! {report_format.upper()} newsletter included.'

                    except Exception as newsletter_error:
                        logger.error(
                            f"Newsletter generation error: {newsletter_error}")
                        with downloads_lock:
                            large_downloads[download_id][
                                'message'] = f'Analysis completed but newsletter generation failed: {str(newsletter_error)}'
                else:
                    with downloads_lock:
                        large_downloads[download_id][
                            'message'] = f'Download completed but no successful AI analyses (0/{len(rtf_contents)})'

            except Exception as ai_error:
                logger.error(f"AI analysis error: {ai_error}")
                with downloads_lock:
                    large_downloads[download_id][
                        'message'] = f'Download completed, but AI analysis failed: {str(ai_error)}'

        # Mark as completed
        with downloads_lock:
            succ = large_downloads[download_id]['succeeded']
            fail = large_downloads[download_id]['failed']
            total = large_downloads[download_id]['total']
        
            large_downloads[download_id].update({
                'status': 'completed',
                'progress': 100,
                'message': f'Successfully downloaded {succ}/{total} cases'
                        + (f', {fail} failed' if fail else '')
                        + (' + AI analysis.' if ai_params and ai_params.get('enable_ai_analysis') else ''),
                'zip_path': zip_path
            })

        logger.info(f"Large download {download_id} completed: {zip_path}")

    except Exception as e:
        logger.error(f"Error in large download {download_id}: {str(e)}")
        with downloads_lock:
            large_downloads[download_id].update({
                'status': 'error',
                'error': str(e),
                'message': f'Error: {str(e)}'
            })


@app.route('/large-download')
def large_download_status():
    """Show large download progress page"""
    download_id = session.get('download_id')
    if not download_id or download_id not in large_downloads:
        return redirect(url_for('index'))

    return render_template('download.html', download_id=download_id)


@app.route('/large-progress/<download_id>')
def get_large_progress(download_id):
    """API endpoint to get large download progress"""
    if download_id not in large_downloads:
        return jsonify({'error': 'Download not found'}), 404

    with downloads_lock:
        return jsonify(large_downloads[download_id])


@app.route('/large-download-file/<download_id>')
def download_large_file(download_id):
    """Download the completed large ZIP file"""
    logger.info(f"Download request for ID: {download_id}")

    # First, try to get from memory
    zip_path = None
    with downloads_lock:
        if download_id in large_downloads:
            progress_info = large_downloads[download_id]
            logger.info(
                f"Progress info: status={progress_info['status']}, zip_path={progress_info['zip_path']}"
            )

            if progress_info['status'] == 'completed' and progress_info['zip_path']:
                zip_path = progress_info['zip_path']

    # If not in memory, try to find file in temp directories (fallback for server restarts)
    if not zip_path:
        logger.info(
            f"Download ID not in memory, searching filesystem for {download_id}"
        )
        import glob
        # Search for files that might match this download
        temp_files = glob.glob(f"/tmp/*/cbosa_large_download_*.zip")
        for temp_file in temp_files:
            # Check if file was created recently (within last 2 hours)
            file_age = time.time() - os.path.getmtime(temp_file)
            if file_age < 7200:  # 2 hours
                zip_path = temp_file
                logger.info(f"Found recent ZIP file: {zip_path}")
                break

    if not zip_path:
        logger.error(f"No ZIP file found for download ID {download_id}")
        return "Download not found", 404

    # Check if file exists
    if not os.path.exists(zip_path):
        logger.error(f"ZIP file not found at path: {zip_path}")
        return "File not found", 404

    try:
        logger.info(f"Sending file: {zip_path}")
        return send_file(zip_path,
                         as_attachment=True,
                         download_name=os.path.basename(zip_path),
                         mimetype='application/zip')
    except Exception as e:
        logger.error(f"Error sending large file: {str(e)}")
        return "Error downloading file", 500

@app.get("/api/judges")
def api_judges():
    q = request.args.get("q", "", type=str).strip()
    court = request.args.get("court", "", type=str).strip()
    limit = request.args.get("limit", default=12, type=int)

    if len(q) < 2:
        return jsonify({"items": []})

    pool = JUDGES_BY_COURT.get(court) or JUDGES_BY_COURT.get("dowolny") or []
    nq = _norm(q)

    out = []
    seen = set()

    for j in pool:
        disp = j.get("display", "")
        if _is_garbage(disp):
            continue

        fn = j.get("first_names", "")
        ln = j.get("last_name", "")
        role = j.get("role", "")

        nd = _norm(disp)
        nfn = _norm(fn)
        nln = _norm(ln)

        tokens = nq.split()
        def matches():
            if all(nd.find(t) != -1 for t in tokens):
                return True
            joined = f"{nfn} {nln}".strip()
            if all(joined.find(t) != -1 for t in tokens):
                return True
            return False

        if not matches():
            continue

        key = (nd, role)
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "label": disp,
            "role": "",
            "first_names": fn,
            "last_name": ln,
        })

        if len(out) >= limit:
            break

    def sort_key(x):
        nd = _norm(x["label"])
        starts = nd.startswith(nq)
        return (0 if starts else 1, _norm(x.get("last_name","")), _norm(x.get("first_names","")))

    out.sort(key=sort_key)
    return jsonify({"items": out})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
