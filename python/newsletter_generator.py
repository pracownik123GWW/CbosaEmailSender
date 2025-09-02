import os
import logging
from datetime import datetime
from typing import List, Dict, Optional

class NewsletterGenerator:
    def __init__(self):
        """Initialize the newsletter generator."""
        self.logger = logging.getLogger(__name__)
        
    def create_html_newsletter(self, analyses: List[Dict], search_params: Dict, stats: Dict) -> str:
        """
        Generate HTML newsletter with AI analyses.
        
        Args:
            analyses: List of analysis results
            search_params: Original search parameters
            stats: Analysis statistics
            
        Returns:
            HTML content as string
        """
        try:
            current_date = datetime.now().strftime('%d.%m.%Y')
            
            html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Biuletyn Analityczny CBOSA</title>
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        
        .newsletter-header {{ 
            background: linear-gradient(135deg, #2c3e50, #3498db); 
            color: white;
            padding: 2rem; 
            margin-bottom: 2rem; 
            border-radius: 10px;
            text-align: center;
        }}
        
        .newsletter-header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.2rem;
        }}
        
        .newsletter-header p {{
            margin: 5px 0;
            opacity: 0.9;
        }}
        
        .analysis-card {{ 
            background-color: white;
            border-left: 4px solid #3498db; 
            margin-bottom: 2rem; 
            padding: 1.5rem; 
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        
        .analysis-title {{ 
            color: #2c3e50; 
            font-size: 1.3rem; 
            font-weight: bold; 
            margin-bottom: 1rem; 
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 0.5rem;
        }}
        
        .analysis-content {{ 
            line-height: 1.7; 
            white-space: pre-line; 
            color: #444;
        }}
        
        .meta-info {{ 
            color: #888; 
            font-size: 0.9rem; 
            margin-bottom: 1rem; 
            font-style: italic;
        }}
        
        .disclaimer {{
            background-color: #e8f4f8;
            border: 1px solid #3498db;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
            font-size: 0.9rem;
        }}
        
        .footer {{
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 2px solid #ecf0f1;
            text-align: center;
            color: #888;
            font-size: 0.9rem;
        }}
        
        .stats-summary {{
            background-color: #f8f9fa;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
            border-left: 4px solid #28a745;
        }}
    </style>
</head>
<body>
    <div class="newsletter-header">
        <h1>🏛️ Biuletyn Analityczny CBOSA</h1>
        <p class="lead">Analiza Orzeczeń Sądów Administracyjnych</p>
        <p><strong>Data:</strong> {current_date} | <strong>Liczba orzeczeń:</strong> {len(analyses)}</p>
    </div>
    
    <div class="disclaimer">
        <strong>🤖 Automatyczna analiza AI:</strong> 
        Ten biuletyn został wygenerowany automatycznie przy użyciu sztucznej inteligencji ChatGPT. 
        Analiza ma charakter pomocniczy i nie zastępuje profesjonalnej interpretacji prawnej.
    </div>
"""

            # Add statistics summary if available
            if stats:
                html_content += f"""
    <div class="stats-summary">
        <h3>📊 Podsumowanie analizy</h3>
        <p><strong>Przeanalizowano:</strong> {stats.get('successful_analyses', 0)} z {stats.get('total_analyses', 0)} orzeczeń</p>
        <p><strong>Współczynnik sukcesu:</strong> {stats.get('success_rate', 0):.1f}%</p>
        <p><strong>Tokeny użyte:</strong> {stats.get('total_tokens_used', 0):,}</p>
        <p><strong>Szacowany koszt:</strong> ${stats.get('estimated_cost_usd', 0):.4f} (~{stats.get('estimated_cost_pln', 0):.2f} PLN)</p>
    </div>
"""

            # Add each analysis
            for i, analysis in enumerate(analyses, 1):
                case_info = analysis.get('case_info', {})
                filename = case_info.get('signature', f'Orzeczenie_{i}')
                case_url = case_info.get('url', '')
                
                html_content += f"""
    <div class="analysis-card">
        <div class="analysis-title">
            📄 Orzeczenie {i}: {filename}
        </div>
        <div class="meta-info">
            🔗 Źródło: {case_url[:60]}{'...' if len(case_url) > 60 else ''}
        </div>
        <div class="analysis-content">
{analysis['analysis']}
        </div>
    </div>
"""

            html_content += """
    <div class="footer">
        <p>
            🔧 Biuletyn wygenerowany przez CBOSA Bot z analizą AI ChatGPT
        </p>
        <p>
            📧 System automatycznego wysyłania biuletynów co poniedziałek o 7:00
        </p>
    </div>
</body>
</html>
"""

            self.logger.info(f"HTML newsletter generated with {len(analyses)} analyses")
            return html_content
            
        except Exception as e:
            self.logger.error(f"Error generating HTML newsletter: {e}")
            raise

    def generate_newsletter(self, analyses: List[Dict], search_params: Dict, stats: Dict) -> str:
        """
        Generate newsletter in HTML format.
        
        Args:
            analyses: List of analysis results
            search_params: Original search parameters
            stats: Analysis statistics
            
        Returns:
            HTML content as string
        """
        return self.create_html_newsletter(analyses, search_params, stats)
