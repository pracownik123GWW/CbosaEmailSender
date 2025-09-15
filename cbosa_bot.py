#!/usr/bin/env python3
"""
Główny moduł orchestracji CBOSA Bot
Koordynuje scrapowanie, analizę AI i wysyłkę newsletterów
"""

import os
import sys
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from string import Template
import traceback

# Dodaj ścieżkę do modułów Python
sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))

from database import DatabaseManager, SearchConfiguration
from brevo_service import BrevoEmailService, EmailRecipient
from cbosa_scraper.cbosa_scraper import CBOSAScraper
from cbosa_scraper.ai_judgment_analyzer import JudgmentAnalyzer
from cbosa_scraper.attachments import EmailAttachmentBuilder

class CBOSABot:
    """Główna klasa orchestracji CBOSA Bot"""
    
    def __init__(self, db_manager: DatabaseManager, email_service: BrevoEmailService):
        self.db_manager = db_manager
        self.email_service = email_service
        self.scraper = CBOSAScraper(delay_between_requests=0.5)
        self.analyzer = JudgmentAnalyzer()
        self.attachments_builder = EmailAttachmentBuilder(output_dir="./out")
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("🤖 CBOSA Bot zainicjalizowany")
    
    def execute_scheduled_run(self):
        """Wykonaj zaplanowane uruchomienie bota"""
        self.logger.info("🤖 Rozpoczęcie zaplanowanego uruchomienia CBOSA Bot...")
        
        try:
            # Pobierz wszystkie aktywne konfiguracje wyszukiwania
            search_configs = self.db_manager.get_all_active_search_configurations()
            
            if not search_configs:
                self.logger.warning("⚠️ Nie znaleziono aktywnych konfiguracji wyszukiwania")
                return
            
            self.logger.info(f"📋 Znaleziono {len(search_configs)} aktywnych konfiguracji wyszukiwania")
            
            # Wykonaj każdą konfigurację wyszukiwania
            for config in search_configs:
                self.execute_search_configuration(config)
            
            self.logger.info("✅ Zaplanowane uruchomienie zakończone pomyślnie")
            
        except Exception:
            self.logger.exception("❌ Błąd podczas zaplanowanego uruchomienia")
            raise
    
    def execute_search_configuration(self, config: SearchConfiguration) -> Dict[str, Any]:
        """
        Wykonaj pojedynczą konfigurację wyszukiwania
        
        Args:
            config: Konfiguracja wyszukiwania
            
        Returns:
            Wyniki wykonania
        """
        self.logger.info(f"🔍 Wykonywanie konfiguracji wyszukiwania: {config.name}")
        
        # Utwórz log wykonania
        execution_log = self.db_manager.create_execution_log(
            search_config_id=config.id,
            status='started'
        )
        
        results = {
            'success': False,
            'execution_log_id': execution_log.id,
            'cases_found': 0,
            'cases_analyzed': 0,
            'emails_sent': 0,
            'errors': []
        }
        
        try:
            # Krok 1: Scrapowanie CBOSA
            self.logger.info("📥 Scrapowanie CBOSA w poszukiwaniu orzeczeń...")
            case_data = self.scraper.search_cases(
                config.search_params,
                date_range=config.date_range,
                max_results=config.max_results
            )
            
            if not case_data:
                self.logger.info("📭 Nie znaleziono orzeczeń dla tej konfiguracji wyszukiwania")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_found'] = len(case_data)
            self.logger.info(f"📊 Znaleziono {results['cases_found']} orzeczeń")
            
            # Pobierz treści RTF
            self.logger.info("📄 Pobieranie treści orzeczeń...")
            download_results = self.scraper.download_multiple_cases(case_data)
            successful_downloads = [r for r in download_results if r['success']]
            
            if not successful_downloads:
                self.logger.warning("⚠️ Nie udało się pobrać żadnych treści orzeczeń")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            self.logger.info(f"✅ Pobrano {len(successful_downloads)} treści orzeczeń")
            
            # Krok 2: Analiza AI
            self.logger.info("🧠 Analiza orzeczeń za pomocą AI...")
            analysis_result = self._analyze_cases_with_ai(successful_downloads)
            
            if not analysis_result['analyses']:
                self.logger.warning("⚠️ Nie wygenerowano żadnych udanych analiz")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_analyzed'] = len(analysis_result['analyses'])
            self.logger.info(f"✅ Przeanalizowano {results['cases_analyzed']} orzeczeń")
            
            self.logger.info("📎 Budowanie załączników (DOCX, TXT, ZIP)...")
            attachments_triplets = self.attachments_builder.build_all(
                analyses=analysis_result['analyses'],
                search_params=config.search_params,
                stats=analysis_result['stats'],
                successful_downloads=successful_downloads
            )
            # BrevoEmailService (jeśli oczekuje listy (filename, bytes)):
            attachments = [(name, data) for (name, data, _mime) in attachments_triplets]

            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            html_tpl_path = os.path.join(templates_dir, "email_body.html")

            now = datetime.now(timezone.utc)
            context = {
                "date_str": now.strftime("%d.%m.%Y"),
                "config_name": config.name,
                "cases_count": str(results['cases_analyzed']),
                "cases_without_justification": str(analysis_result['stats'].get('cases_without_justification', 0)),
                "hello_line": f"{config.name},",
                "sender_name": "CBOSA Biuletyn",
                "contact_email": "marketing@gww.pl",
                "support_email": "marketing@gww.pl",
            }

            email_body = CBOSABot.render_file_template(html_tpl_path, context)
            
            # Krok 4: Wysyłka newsletterów
            self.logger.info("📧 Wysyłanie newsletterów do subskrybentów...")
            subscribers = self.db_manager.get_subscriptions_for_config(config.id)
            
            if not subscribers:
                self.logger.info("📪 Brak subskrybentów dla tej konfiguracji wyszukiwania")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            # Pobierz szczegóły użytkowników-subskrybentów
            recipients = []
            for subscription in subscribers:
                user = self.db_manager.get_user(subscription.user_id)
                if user and user.is_active:
                    recipients.append(EmailRecipient(
                        email=user.email,
                        name=user.name
                    ))
            
            if not recipients:
                self.logger.info("📪 Brak aktywnych subskrybentów dla tej konfiguracji")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            # Wyślij newslettery
            email_results = self.email_service.send_bulk_newsletter(
                recipients=recipients,
                email_body=email_body,
                config_name=config.name,
                attachments=attachments
            )
            
            # Zapisz logi emaili
            for i, email_result in enumerate(email_results):
                recipient = recipients[i]
                user = next((u for u in [self.db_manager.get_user_by_email(recipient.email)] if u), None)
                
                if user:
                    self.db_manager.create_email_log(
                        execution_log_id=execution_log.id,
                        user_id=user.id,
                        email=recipient.email,
                        status='sent' if email_result.success else 'failed',
                        brevo_message_id=email_result.message_id,
                        error_message=email_result.error
                    )
                    
                    if email_result.success:
                        results['emails_sent'] += 1
                    else:
                        results['errors'].append(f"Email do {recipient.email}: {email_result.error}")
            
            results['success'] = True
            self.logger.info(f"📬 Wysłano {results['emails_sent']} newsletterów pomyślnie")
            
            # Zaktualizuj log wykonania z sukcesem
            self._update_execution_log_completed(execution_log.id, results)
            
            return results
            
        except Exception as e:
            self.logger.exception("❌ Błąd podczas wykonywania konfiguracji")
            results["errors"].append({
                "message": str(e),
                "traceback": traceback.format_exc()
            })
            
            # Zaktualizuj log wykonania z błędem
            self.db_manager.update_execution_log(
                log_id=execution_log.id,
                status='failed',
                completed_at=datetime.now(timezone.utc),
                cases_found=results['cases_found'],
                cases_analyzed=results['cases_analyzed'],
                emails_sent=results['emails_sent'],
                error_message=str(e),
                execution_details={'errors': results['errors']}
            )
            
            raise
        
        finally:
            # cleanup temporary files
            self.attachments_builder.cleanup()
    
    def _analyze_cases_with_ai(self, cases_data: List[Dict]) -> Dict[str, Any]:
        """
        Analizuj orzeczenia za pomocą AI
        
        Args:
            cases_data: Lista pobranych orzeczeń
            
        Returns:
            Wyniki analizy
        """
        try:
            self.logger.info(f"🧠 Rozpoczęcie analizy AI {len(cases_data)} orzeczeń")
            
            # Przygotuj orzeczenia do analizy
            judgments = []
            for case_data in cases_data:
                if case_data['content']:
                    content = case_data['content']
                    if isinstance(content, bytes):
                        content = content.decode('utf-8', errors='ignore')
                    
                    judgments.append({
                        'content': content,
                        'case_info': case_data['case_info']
                    })
            
            # Analizuj wszystkie orzeczenia
            analysis_results = self.analyzer.analyze_multiple_judgments(judgments)
            
            # Oblicz statystyki
            stats = self.analyzer.calculate_analysis_stats(analysis_results)
            
            # Filtruj udane analizy
            successful_analyses = [r for r in analysis_results if r['success']]
            
            self.logger.info(f"✅ Analiza zakończona: {len(successful_analyses)} udanych analiz")
            
            return {
                'analyses': successful_analyses,
                'stats': stats,
                'all_results': analysis_results
            }
            
        except Exception:
            self.logger.exception("❌ Błąd w analizie AI")
            raise
    
    def _update_execution_log_completed(self, log_id: str, results: Dict[str, Any]):
        """Zaktualizuj log wykonania jako zakończony"""
        self.db_manager.update_execution_log(
            log_id=log_id,
            status='completed' if results['success'] else 'failed',
            completed_at=datetime.utcnow(),
            cases_found=results['cases_found'],
            cases_analyzed=results['cases_analyzed'],
            emails_sent=results['emails_sent'],
            error_message='; '.join(results['errors']) if results['errors'] else None,
            execution_details={'errors': results['errors']}
        )

    @staticmethod
    def render_file_template(path: str, context: Dict[str, str]) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Template not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            tpl = Template(f.read())
        # safe_substitute = brak Exception gdy jakiś placeholder nie wystąpi w kontekście
        return tpl.safe_substitute(context)
