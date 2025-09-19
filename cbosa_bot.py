#!/usr/bin/env python3
"""
Główny moduł orchestracji CBOSA Bot
Koordynuje scrapowanie, analizę AI i wysyłkę newsletterów
"""

import os
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
            
            # Krok 4: Budowanie załączników (DOCX, ZIP)
            self.logger.info("📎 Budowanie załączników (DOCX, ZIP)...")
            attachments_triplets = self.attachments_builder.build_all(
                analyses=analysis_result['analyses'],
                search_params=config.config,
                stats=analysis_result['stats'],
                successful_downloads=successful_downloads
            )
            # BrevoEmailService (jeśli oczekuje listy (filename, bytes)):
            attachments = [(name, data) for (name, data, _mime) in attachments_triplets]
            
            # Krok 5: Wysyłka newsletterów do wszystkich subskrybentów
            self.logger.info("📧 Wysyłanie newsletterów do subskrybentów...")
            subscribers = self.db_manager.get_subscriptions_for_config(config.id)
            
            if not subscribers:
                self.logger.info("📪 Brak subskrybentów dla tej konfiguracji wyszukiwania")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            # Przygotowanie szablonu email (raz dla wszystkich)
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            html_tpl_path = os.path.join(templates_dir, "email_body.html")
            now = datetime.now(timezone.utc)
            
            # Wysyłka do każdego subskrybenta z personalizacją
            email_results = []
            for subscription in subscribers:
                user = self.db_manager.get_user(subscription.user_id)
                if not user or not user.is_active:
                    continue
                    
                # Personalizowany szablon dla każdego użytkownika
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
                
                # Wysyłka pojedynczego emaila
                recipient = EmailRecipient(email=user.email, name=full_name or user.email)
                
                if hasattr(self.email_service, "send_newsletter"):
                    email_result = self.email_service.send_newsletter(
                        recipient=recipient,
                        email_body=email_body,
                        config_name=config.short_name,
                        attachments=attachments
                    )
                else:
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
                
                email_results.append(email_result)
            
            # Zapisz logi emaili  
            active_subscribers = [s for s in subscribers if self.db_manager.get_user(s.user_id) and self.db_manager.get_user(s.user_id).is_active]
            for i, email_result in enumerate(email_results):
                subscription = active_subscribers[i]
                user = self.db_manager.get_user(subscription.user_id)
                
                if user:
                    self.db_manager.create_email_log(
                        execution_log_id=execution_log.id,
                        user_id=user.id,
                        email=user.email,
                        status='sent' if email_result.success else 'failed',
                        brevo_message_id=email_result.message_id,
                        error_message=email_result.error
                    )
                    
                    if email_result.success:
                        results['emails_sent'] += 1
                    else:
                        results['errors'].append(f"Email do {user.email}: {email_result.error}")
            
            results['success'] = True
            self.logger.info(f"📬 Wysłano {results['emails_sent']} newsletterów pomyślnie")
            
            # Zaktualizuj log wykonania z sukcesem
            self._update_execution_log_completed(execution_log.id, results)
            
            # Wysyłka spóźnionych uzasadnień
            try:
                pending_stats = self._process_pending_justifications(config, execution_log.id)
                # jeśli chcesz, możesz doliczyć to do 'results' / statusu
                results['emails_sent'] += pending_stats.get('emails_sent', 0)
                self.logger.info(
                    "📌 Backlog: sprawdzono=%d, resolved=%d, wysłane=%d",
                    pending_stats.get('pendings_checked', 0),
                    pending_stats.get('resolved', 0),
                    pending_stats.get('emails_sent', 0),
                )
            except Exception:
                self.logger.exception("❌ Błąd podczas przetwarzania pendingów (spóźnione uzasadnienia)")
            
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
    
    def _process_pending_justifications(self, config, execution_log_id: int) -> Dict[str, int]:
        """
        Szuka spóźnionych uzasadnień dla pendingów danej konfiguracji.
        Jeśli znajdzie – pobiera RTF, analizuje, buduje osobny DOCX i wysyła osobny newsletter.
        Zwraca statystyki {'pendings_checked': X, 'resolved': Y, 'emails_sent': Z}.
        """
        stats = {"pendings_checked": 0, "resolved": 0, "emails_sent": 0}
        pendings = self.db_manager.get_pending_for_config(config.id)

        if not pendings:
            self.logger.info("🗂️ Brak pendingów do sprawdzenia dla: %s", config.short_name)
            return stats

        self.logger.info("🔁 Sprawdzanie pendingów (%d) dla: %s", len(pendings), config.short_name)

        resolved_items = []

        for pj in pendings:
            stats["pendings_checked"] += 1
            sig = pj.signature
            try:
                if self.scraper.has_justification_for_signature(sig):
                    # spróbuj z istniejącego URL
                    rtf = self.scraper.download_case_rtf(pj.url)
                    case_url = pj.url

                    # fallback: znajdź „świeży” URL po sygnaturze
                    if not rtf:
                        found = self.scraper.get_case_by_signature(sig)
                        if found:
                            case_url = found["url"]
                            rtf = self.scraper.download_case_rtf(case_url)

                    if not rtf:
                        # coś nie gra – raportuj i zostaw jako NO_JUSTIFICATION (sprawdzimy następnym razem)
                        self.logger.warning("⚠️ Znalazłem uzasadnienie dla %s, ale nie pobrałem RTF.", sig)
                        self.db_manager.touch_pending_no_justification(pj.id)
                        continue

                    resolved_items.append({
                        "pending": pj,
                        "case_info": {"url": case_url, "signature": sig},
                        "content": rtf
                    })
                else:
                    # dalej brak – odnotuj sprawdzenie
                    self.db_manager.touch_pending_no_justification(pj.id)

            except Exception as e:
                self.logger.exception("Błąd przy sprawdzaniu pendingu %s: %s", sig, e)
                self.db_manager.touch_pending_no_justification(pj.id)

        if not resolved_items:
            self.logger.info("ℹ️ Brak uzasadnień, które się pojawiły dla: %s", config.short_name)
            return stats

        # Analiza AI
        judgments = []
        for item in resolved_items:
            content = item["content"]
            if isinstance(content, bytes):
                try:
                    content = content.decode("utf-8", errors="ignore")
                except Exception:
                    pass
            judgments.append({"content": content, "case_info": item["case_info"]})

        analysis_results = self.analyzer.analyze_multiple_judgments(judgments)
        successful = [r for r in analysis_results if r.get("success")]
        if not successful:
            self.logger.warning("⚠️ Nie udało się przeanalizować żadnego „spóźnionego” uzasadnienia.")
            return stats

        stats["resolved"] = len(successful)

        # Zbuduj załączniki (DOCX/TXT/ZIP) – i zmień nazwę DOCX na „konkretną”
        computed_stats = self.analyzer.calculate_analysis_stats(analysis_results)
        downloads_like = [
            {"case_info": it["case_info"], "content": it["content"], "success": True}
            for it in resolved_items
        ]
        attachments_triplets = self.attachments_builder.build_all(
            analyses=successful,
            search_params=config.config,
            stats=computed_stats,
            successful_downloads=downloads_like
        )
        # BrevoEmailService oczekuje listy (name, bytes)
        # Zmieniamy nazwę DOCX, żeby odbiorca od razu widział, że to partia „zaległych uzasadnień”
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        attachments = []
        for (name, data, mime) in attachments_triplets:
            if name.lower().endswith(".docx"):
                name = f"{config.short_name} – Uzasadnienia (starsze) – {date_str}.docx"
            attachments.append((name, data))

        # Wyślij osobny newsletter do subskrybentów tej konfiguracji
        subscribers = self.db_manager.get_subscriptions_for_config(config.id)
        if not subscribers:
            self.logger.info("📪 Brak subskrybentów dla drugiego newslettera (%s)", config.short_name)
        else:
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
            html_tpl_path = os.path.join(templates_dir, "email_body.html")
            now = datetime.now(timezone.utc)
            config_label = f"{config.short_name} – Uzasadnienia dla starszych orzeczeń"

            for subscription in subscribers:
                user = self.db_manager.get_user(subscription.user_id)
                if not user or not user.is_active:
                    continue

                full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
                hello_line = full_name if full_name else "Szanowni Państwo"

                context = {
                    "date_str": now.strftime("%d.%m.%Y"),
                    "config_name": config_label,
                    "cases_count": str(len(successful)),
                    "cases_without_justification": "0",
                    "hello_line": f"{hello_line},",
                    "sender_name": "CBOSA Biuletyn",
                    "contact_email": "marketing@gww.pl",
                    "support_email": "marketing@gww.pl",
                }
                email_body = CBOSABot.render_file_template(html_tpl_path, context)

                recipient = EmailRecipient(email=user.email, name=full_name or user.email)

                # używamy 'config_name' jako temat: „Biuletyn CBOSA: {config_name} – {data}”
                email_result = self.email_service.send_newsletter(
                    recipient=recipient,
                    email_body=email_body,
                    config_name=config_label,
                    attachments=attachments
                )

                self.db_manager.create_email_log(
                    execution_log_id=execution_log_id,
                    user_id=user.id,
                    email=recipient.email,
                    status='sent' if email_result.success else 'failed',
                    brevo_message_id=getattr(email_result, "message_id", None),
                    error_message=getattr(email_result, "error", None)
                )
                if email_result.success:
                    stats["emails_sent"] += 1

        # Na końcu – oznacz rozwiązaną partię jako PROCESSED
        for item in resolved_items:
            self.db_manager.mark_pending_as_processed(item["pending"].id)

        self.logger.info(
            "📨 Pendingi: sprawdzono=%d, uzasadnienia znalezione=%d, maile=%d",
            stats["pendings_checked"], stats["resolved"], stats["emails_sent"]
        )
        return stats


    @staticmethod
    def render_file_template(path: str, context: Dict[str, str]) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Template not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            tpl = Template(f.read())
        # safe_substitute = brak Exception gdy jakiś placeholder nie wystąpi w kontekście
        return tpl.safe_substitute(context)
