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

# Import modułów CBOSA

from database import DatabaseManager
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
        """Wykonaj zaplanowane uruchomienie bota - zoptymalizowana wersja"""
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
    
    def execute_search_configuration(self, config):
        """Wykonaj pojedynczą konfigurację wyszukiwania - zoptymalizowana wersja"""
        self.logger.info(f"🔍 Wykonywanie konfiguracji wyszukiwania: {config.short_name}")
        
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
                config.config,
                config.date_range,
                max_results=config.max_results
            )
            
            if not case_data:
                self.logger.info("📭 Nie znaleziono orzeczeń dla tej konfiguracji wyszukiwania")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_found'] = len(case_data)
            self.logger.info(f"📊 Znaleziono {results['cases_found']} orzeczeń")
            
            # Krok 2: Pobieranie treści RTF
            self.logger.info("📄 Pobieranie treści orzeczeń...")
            download_results = self.scraper.download_multiple_cases(case_data)
            successful_downloads = [r for r in download_results if r['success']]
            
            if not successful_downloads:
                self.logger.warning("⚠️ Nie udało się pobrać żadnych treści orzeczeń")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            self.logger.info(f"✅ Pobrano {len(successful_downloads)} treści orzeczeń")
            
            # Krok 3: Analiza AI  
            self.logger.info("🧠 Analiza orzeczeń za pomocą AI...")
            analysis_result = self._analyze_cases_with_ai(successful_downloads)
            
            if not analysis_result['analyses']:
                self.logger.warning("⚠️ Nie wygenerowano żadnych udanych analiz")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_analyzed'] = len(analysis_result['analyses'])
            self.logger.info(f"✅ Przeanalizowano {results['cases_analyzed']} orzeczeń")
            
            # Krok 4: Generowanie newslettera HTML
            self.logger.info("📄 Generowanie newslettera HTML...")
            newsletter_html = self._generate_simple_newsletter_html(
                analyses=analysis_result['analyses'],
                config_name=config.short_name,
                stats=analysis_result['stats']
            )
            
            # Krok 5: Wysyłka newsletterów do wszystkich subskrybentów
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
            
            # Wyślij newsletter do wszystkich subskrybentów tej konfiguracji
            email_results = self.email_service.send_bulk_newsletter(
                recipients=recipients,
                newsletter_html=newsletter_html,
                config_name=config.short_name
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
            self.logger.error(f"❌ Błąd podczas wykonywania konfiguracji {config.short_name}: {e}")
            results['errors'].append(str(e))
            
            # Zaktualizuj log wykonania z błędem
            self.db_manager.update_execution_log(
                log_id=execution_log.id,
                status='failed',
                completed_at=datetime.utcnow(),
                cases_found=results['cases_found'],
                cases_analyzed=results['cases_analyzed'],
                emails_sent=results['emails_sent'],
                error_message=str(e),
                execution_details={'errors': results['errors']}
            )
            
            raise
    #         templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    #         html_tpl_path = os.path.join(templates_dir, "email_body.html")

    #         for subscription in subscribers:
    #             user = self.db_manager.get_user(subscription.user_id)
    #             if not user or not user.is_active:
    #                 continue

    #             full_name = f"{user.first_name} {user.last_name}".strip()
    #             hello_line = full_name if full_name else "Szanowni Państwo"

    #             # 👇 personalizowany kontekst dla każdego użytkownika
    #             context = {
    #                 "date_str": now.strftime("%d.%m.%Y"),
    #                 "config_name": config.short_name,
    #                 "cases_count": str(results['cases_analyzed']),
    #                 "cases_without_justification": str(analysis_result['stats'].get('cases_without_justification', 0)),
    #                 "hello_line": f"{hello_line},",
    #                 "sender_name": "CBOSA Biuletyn",
    #                 "contact_email": "marketing@gww.pl",
    #                 "support_email": "marketing@gww.pl",
    #             }

    #             email_body = CBOSABot.render_file_template(html_tpl_path, context)

    #             # wysyłka do pojedynczego użytkownika
    #             recipient = EmailRecipient(email=user.email, name=full_name or user.email)
    #             email_result = self.email_service.send_newsletter(  # 👈 zamiast send_bulk_newsletter
    #                 recipient=recipient,
    #                 email_body=email_body,
    #                 config_name=config.short_name,
    #                 attachments=attachments
    #             )

    #             # logowanie
    #             self.db_manager.create_email_log(
    #                 execution_log_id=execution_log.id,
    #                 user_id=user.id,
    #                 email=recipient.email,
    #                 status='sent' if email_result.success else 'failed',
    #                 brevo_message_id=email_result.message_id,
    #                 error_message=email_result.error
    #             )

    #             if email_result.success:
    #                 results['emails_sent'] += 1
    #             else:
    #                 results['errors'].append(f"Email do {recipient.email}: {email_result.error}")
            
    #         results['success'] = True
    #         self.logger.info(f"📬 Wysłano {results['emails_sent']} newsletterów pomyślnie")
            
    #         # Zaktualizuj log wykonania z sukcesem
    #         self._update_execution_log_completed(execution_log.id, results)
            
    #         return results
            
    #     except Exception as e:
    #         self.logger.exception("❌ Błąd podczas wykonywania konfiguracji")
    #         results["errors"].append({
    #             "message": str(e),
    #             "traceback": traceback.format_exc()
    #         })
            
    #         # Zaktualizuj log wykonania z błędem
    #         self.db_manager.update_execution_log(
    #             log_id=execution_log.id,
    #             status='failed',
    #             completed_at=datetime.now(timezone.utc),
    #             cases_found=results['cases_found'],
    #             cases_analyzed=results['cases_analyzed'],
    #             emails_sent=results['emails_sent'],
    #             error_message=str(e),
    #             execution_details={'errors': results['errors']}
    #         )
            
    #         raise
        
    #     finally:
    #         # cleanup temporary files
    #         self.attachments_builder.cleanup()
    
    def execute_subscription(self, subscription) -> Dict[str, Any]:
        """
        Wykonaj pojedynczą subskrypcję (user ↔ search_config):
        - scrapuje według konfiguracji subskrypcji,
        - analizuje,
        - buduje załączniki,
        - wysyła JEDEN spersonalizowany email do użytkownika.
        """
        user = subscription.user
        config = subscription.search_config

        # Walidacje subskrypcji / użytkownika / konfiguracji
        if not subscription.is_active or not user or not user.is_active or not config or not config.is_active:
            self.logger.info("⏭️ Pominięto subskrypcję (nieaktywna / brak usera lub konfiguracji)")
            return {
                'success': False,
                'execution_log_id': None,
                'cases_found': 0,
                'cases_analyzed': 0,
                'emails_sent': 0,
                'errors': ["Inactive subscription/user/config or missing data"]
            }

        self.logger.info(
            f"🔔 Subskrypcja: user={user.email} ⇄ config={config.short_name}"
        )

        # Utwórz log wykonania per konfiguracja (jeden log na subskrypcję)
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
            # 1) Scrapowanie CBOSA
            self.logger.info("📥 Scrapowanie CBOSA…")
            case_data = self.scraper.search_cases(
                config.config,
                date_range=config.date_range,
                max_results=config.max_results
            )

            if not case_data:
                self.logger.info("📭 Brak orzeczeń dla tej subskrypcji")
                self._update_execution_log_completed(execution_log.id, results)
                return results

            results['cases_found'] = len(case_data)
            self.logger.info(f"📊 Znaleziono {results['cases_found']} orzeczeń")

            # 2) Pobranie treści
            self.logger.info("📄 Pobieranie treści orzeczeń…")
            download_results = self.scraper.download_multiple_cases(case_data)
            successful_downloads = [r for r in download_results if r['success']]

            if not successful_downloads:
                self.logger.warning("⚠️ Nie udało się pobrać żadnych treści orzeczeń")
                self._update_execution_log_completed(execution_log.id, results)
                return results

            self.logger.info(f"✅ Pobrano {len(successful_downloads)} treści orzeczeń")

            # 3) Analiza AI
            self.logger.info("🧠 Analiza orzeczeń…")
            analysis_result = self._analyze_cases_with_ai(successful_downloads)

            if not analysis_result['analyses']:
                self.logger.warning("⚠️ Brak udanych analiz")
                self._update_execution_log_completed(execution_log.id, results)
                return results

            results['cases_analyzed'] = len(analysis_result['analyses'])
            self.logger.info(f"✅ Przeanalizowano {results['cases_analyzed']} orzeczeń")

            # 4) Załączniki
            self.logger.info("📎 Budowanie załączników (DOCX, ZIP)…")
            attachments_triplets = self.attachments_builder.build_all(
                analyses=analysis_result['analyses'],
                search_params=config.config,
                stats=analysis_result['stats'],
                successful_downloads=successful_downloads
            )
            # BrevoEmailService (jeśli oczekuje listy (filename, bytes)):
            attachments = [(name, data) for (name, data, _mime) in attachments_triplets]

            # 5) Templating maila (spersonalizowany 'hello_line')
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            html_tpl_path = os.path.join(templates_dir, "email_body.html")

            now = datetime.now(timezone.utc)
            full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
            hello_line = full_name if full_name else "Szanowni Państwo"
            context = {
                "date_str": now.strftime("%d.%m.%Y"),
                "config_name": config.short_name,
                "cases_count": str(results['cases_analyzed']),
                "cases_without_justification": str(analysis_result['stats'].get('cases_without_justification', 0)),
                "hello_line": f"{hello_line},",
                "sender_name": "CBOSA Biuletyn",
                "contact_email": "marketing@gww.pl",
                "support_email": "marketing@gww.pl",
            }
            email_body = CBOSABot.render_file_template(html_tpl_path, context)

            # 6) Wysyłka JEDNEGO maila do usera z tej subskrypcji
            recipient = EmailRecipient(email=user.email, name=full_name or user.email)

            # Preferowane: metoda send_newsletter (jeśli masz ją w BrevoEmailService)
            if hasattr(self.email_service, "send_newsletter"):
                email_result = self.email_service.send_newsletter(
                    recipient=recipient,
                    email_body=email_body,
                    config_name=config.short_name,
                    attachments=attachments
                )
            else:
                # Fallback: zbuduj EmailContent i wyślij przez send_email
                from brevo_service import EmailContent
                subject = f"Biuletyn CBOSA: {config.short_name} - {now.strftime('%d.%m.%Y')}"
                email_result = self.email_service.send_email(
                    recipients=[recipient],
                    content=EmailContent(
                        subject=subject,
                        email_body=email_body,
                        text_content="Biuletyn dostępny jest w wersji HTML."
                    ),
                    attachments=attachments
                )[0]

            # 7) Logowanie maila
            self.db_manager.create_email_log(
                execution_log_id=execution_log.id,
                user_id=user.id,
                email=recipient.email,
                status='sent' if email_result.success else 'failed',
                brevo_message_id=getattr(email_result, "message_id", None),
                error_message=getattr(email_result, "error", None)
            )

            if email_result.success:
                results['emails_sent'] = 1
                results['success'] = True
                self.logger.info(f"📬 Wysłano newsletter do: {recipient.email}")
            else:
                results['errors'].append(f"Email do {recipient.email}: {getattr(email_result, 'error', 'unknown error')}")

            # Zakończ log wykonania
            self._update_execution_log_completed(execution_log.id, results)
            return results

        except Exception as e:
            self.logger.exception("❌ Błąd podczas wykonywania subskrypcji")
            results["errors"].append({
                "message": str(e),
                "traceback": traceback.format_exc()
            })
            # Aktualizacja logu z błędem
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
            # sprzątanie plików tymczasowych
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

    def _generate_simple_newsletter_html(self, analyses: List[Dict], config_name: str, stats: Dict) -> str:
        """Generuj prosty newsletter HTML"""
        from datetime import datetime
        
        current_date = datetime.now().strftime('%d.%m.%Y')
        
        html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Biuletyn CBOSA - {config_name}</title>
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
        
        .newsletter-header .date {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}
        
        .summary {{
            background: #e8f4f8;
            border-left: 4px solid #3498db;
            padding: 1.5rem;
            margin-bottom: 2rem;
            border-radius: 5px;
        }}
        
        .judgment-article {{
            background: white;
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #27ae60;
        }}
        
        .judgment-article h2 {{
            color: #2c3e50;
            margin-top: 0;
            font-size: 1.4rem;
            line-height: 1.3;
        }}
        
        .judgment-content {{
            font-size: 1rem;
            line-height: 1.7;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 3rem;
            padding: 2rem;
            background: #34495e;
            color: white;
            border-radius: 5px;
        }}
    </style>
</head>
<body>
    <div class="newsletter-header">
        <h1>📊 Biuletyn CBOSA</h1>
        <div class="date">{current_date} • {config_name}</div>
    </div>
    
    <div class="summary">
        <h3>📋 Podsumowanie</h3>
        <p>Znaleziono i przeanalizowano <strong>{len(analyses)} orzeczeń</strong> zgodnych z kryteriami wyszukiwania.</p>
    </div>
"""

        # Dodaj artykuły z analizami
        for i, analysis in enumerate(analyses, 1):
            analysis_text = analysis.get('analysis', 'Brak analizy')
            
            html_content += f"""
    <div class="judgment-article">
        <h2>Orzeczenie #{i}</h2>
        <div class="judgment-content">
            {self._format_analysis_as_html(analysis_text)}
        </div>
    </div>
"""

        # Dodaj stopkę
        html_content += f"""
    <div class="footer">
        <p>🤖 Automatyczny biuletyn CBOSA Bot</p>
        <p><small>Newsletter wygenerowany automatycznie na podstawie bazy orzeczeń CBOSA</small></p>
    </div>
</body>
</html>
"""
        
        return html_content
    
    def _format_analysis_as_html(self, analysis_text: str) -> str:
        """Sformatuj tekst analizy jako HTML"""
        if not analysis_text:
            return "<p>Brak analizy</p>"
        
        # Zamień nowe linie na paragrafy
        paragraphs = analysis_text.strip().split('\n\n')
        html_paragraphs = []
        
        for paragraph in paragraphs:
            if paragraph.strip():
                html_paragraphs.append(f"<p>{paragraph.strip()}</p>")
        
        return '\n'.join(html_paragraphs)

    @staticmethod
    def render_file_template(path: str, context: Dict[str, str]) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Template not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            tpl = Template(f.read())
        # safe_substitute = brak Exception gdy jakiś placeholder nie wystąpi w kontekście
        return tpl.safe_substitute(context)
