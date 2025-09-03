#!/usr/bin/env python3
"""
Główny moduł orchestracji CBOSA Bot
Koordynuje scrapowanie, analizę AI i wysyłkę newsletterów
"""

import os
import sys
import logging
from typing import List, Dict, Any
from datetime import datetime

# Dodaj ścieżkę do modułów Python
sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))

from database import DatabaseManager, SearchConfiguration, User
from brevo_service import BrevoEmailService, EmailRecipient
from cbosa_scraper.cbosa_scraper import CBOSAScraper
from cbosa_scraper.ai_judgment_analyzer import JudgmentAnalyzer
from cbosa_scraper.newsletter_generator import NewsletterGenerator
from file_helpers import build_judgments_zip

logger = logging.getLogger(__name__)

class CBOSABot:
    """Główna klasa orchestracji CBOSA Bot"""
    
    def __init__(self, db_manager: DatabaseManager, email_service: BrevoEmailService):
        self.db_manager = db_manager
        self.email_service = email_service
        self.scraper = CBOSAScraper(delay_between_requests=0.5)
        self.analyzer = JudgmentAnalyzer()
        self.newsletter_generator = NewsletterGenerator()
        
        logger.info("🤖 CBOSA Bot zainicjalizowany")
    
    def execute_scheduled_run(self):
        """Wykonaj zaplanowane uruchomienie bota"""
        logger.info("🤖 Rozpoczęcie zaplanowanego uruchomienia CBOSA Bot...")
        
        try:
            # Pobierz wszystkie aktywne konfiguracje wyszukiwania
            search_configs = self.db_manager.get_all_active_search_configurations()
            
            if not search_configs:
                logger.warning("⚠️ Nie znaleziono aktywnych konfiguracji wyszukiwania")
                return
            
            logger.info(f"📋 Znaleziono {len(search_configs)} aktywnych konfiguracji wyszukiwania")
            
            # Wykonaj każdą konfigurację wyszukiwania
            for config in search_configs:
                self.execute_search_configuration(config)
            
            logger.info("✅ Zaplanowane uruchomienie zakończone pomyślnie")
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas zaplanowanego uruchomienia: {e}")
            raise
    
    def execute_search_configuration(self, config: SearchConfiguration) -> Dict[str, Any]:
        """
        Wykonaj pojedynczą konfigurację wyszukiwania
        
        Args:
            config: Konfiguracja wyszukiwania
            
        Returns:
            Wyniki wykonania
        """
        logger.info(f"🔍 Wykonywanie konfiguracji wyszukiwania: {config.name}")
        
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
            logger.info("📥 Scrapowanie CBOSA w poszukiwaniu orzeczeń...")
            case_data = self.scraper.search_cases(
                config.search_params,
                max_results=config.max_results
            )
            
            if not case_data:
                logger.info("📭 Nie znaleziono orzeczeń dla tej konfiguracji wyszukiwania")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_found'] = len(case_data)
            logger.info(f"📊 Znaleziono {results['cases_found']} orzeczeń")
            
            # Pobierz treści RTF
            logger.info("📄 Pobieranie treści orzeczeń...")
            download_results = self.scraper.download_multiple_cases(case_data)
            successful_downloads = [r for r in download_results if r['success']]
            
            if not successful_downloads:
                logger.warning("⚠️ Nie udało się pobrać żadnych treści orzeczeń")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            logger.info(f"✅ Pobrano {len(successful_downloads)} treści orzeczeń")
            
            # Krok 2: Analiza AI
            logger.info("🧠 Analiza orzeczeń za pomocą AI...")
            analysis_result = self._analyze_cases_with_ai(successful_downloads)
            
            if not analysis_result['analyses']:
                logger.warning("⚠️ Nie wygenerowano żadnych udanych analiz")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            results['cases_analyzed'] = len(analysis_result['analyses'])
            logger.info(f"✅ Przeanalizowano {results['cases_analyzed']} orzeczeń")
            
            # Krok 3: Generowanie newslettera
            logger.info("📄 Generowanie newslettera...")
            newsletter_html = self.newsletter_generator.generate_newsletter(
                analyses=analysis_result['analyses'],
                search_params=config.search_params,
                stats=analysis_result['stats']
            )
            
            #  Krok 3.5: Zbudowanie ZIP z orzeczeniami
            logger.info("🗜️ Budowanie pliku ZIP z orzeczeniami...")
            zip_bytes, zip_name = build_judgments_zip(successful_downloads)

            attachments = []
            if zip_bytes:
                attachments.append({
                    "filename": zip_name,
                    "content": zip_bytes,
                    "mimetype": "application/zip"
                })
            
            # Krok 4: Wysyłka newsletterów
            logger.info("📧 Wysyłanie newsletterów do subskrybentów...")
            subscribers = self.db_manager.get_subscriptions_for_config(config.id)
            
            if not subscribers:
                logger.info("📪 Brak subskrybentów dla tej konfiguracji wyszukiwania")
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
                logger.info("📪 Brak aktywnych subskrybentów dla tej konfiguracji")
                self._update_execution_log_completed(execution_log.id, results)
                return results
            
            # Wyślij newslettery
            email_results = self.email_service.send_bulk_newsletter(
                recipients=recipients,
                newsletter_html=newsletter_html,
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
            logger.info(f"📬 Wysłano {results['emails_sent']} newsletterów pomyślnie")
            
            # Zaktualizuj log wykonania z sukcesem
            self._update_execution_log_completed(execution_log.id, results)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas wykonywania konfiguracji {config.name}: {e}")
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
    
    def _analyze_cases_with_ai(self, cases_data: List[Dict]) -> Dict[str, Any]:
        """
        Analizuj orzeczenia za pomocą AI
        
        Args:
            cases_data: Lista pobranych orzeczeń
            
        Returns:
            Wyniki analizy
        """
        try:
            logger.info(f"🧠 Rozpoczęcie analizy AI {len(cases_data)} orzeczeń")
            
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
            
            logger.info(f"✅ Analiza zakończona: {len(successful_analyses)} udanych analiz")
            
            return {
                'analyses': successful_analyses,
                'stats': stats,
                'all_results': analysis_results
            }
            
        except Exception as e:
            logger.error(f"❌ Błąd w analizie AI: {e}")
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
    
    def create_default_configurations(self):
        """Utwórz domyślne konfiguracje wyszukiwania"""
        logger.info("📋 Tworzenie domyślnych konfiguracji wyszukiwania...")
        
        default_configs = [
            {
                'name': 'Podatek VAT - Najnowsze Orzeczenia',
                'description': 'Najnowsze orzeczenia dotyczące podatku VAT',
                'search_params': {
                    'keywords': 'VAT podatek',
                    'keywords_location': 'gdziekolwiek',
                    'with_inflection': 'on',
                    'court': 'dowolny',
                    'judgment_type': 'Wyrok',
                    'with_justification': 'on',
                    'date_from': '2024-01-01'
                },
                'max_results': 30
            },
            {
                'name': 'Prawo Budowlane',
                'description': 'Orzeczenia związane z prawem budowlanym i pozwoleniami na budowę',
                'search_params': {
                    'keywords': 'pozwolenie budowa budowlane',
                    'keywords_location': 'gdziekolwiek',
                    'with_inflection': 'on',
                    'court': 'dowolny',
                    'judgment_type': 'Wyrok',
                    'with_justification': 'on'
                },
                'max_results': 25
            },
            {
                'name': 'Podatek Dochodowy',
                'description': 'Orzeczenia dotyczące podatku dochodowego od osób fizycznych i prawnych',
                'search_params': {
                    'keywords': 'podatek dochodowy PIT CIT',
                    'keywords_location': 'gdziekolwiek',
                    'with_inflection': 'on',
                    'court': 'dowolny',
                    'judgment_type': 'Wyrok',
                    'with_justification': 'on',
                    'date_from': '2024-01-01'
                },
                'max_results': 35
            }
        ]
        
        for config_data in default_configs:
            try:
                # Sprawdź czy konfiguracja już istnieje
                existing_configs = self.db_manager.get_all_active_search_configurations()
                if any(c.name == config_data['name'] for c in existing_configs):
                    logger.info(f"⚪ Konfiguracja '{config_data['name']}' już istnieje")
                    continue
                
                # Utwórz nową konfigurację
                config = self.db_manager.create_search_configuration(
                    name=config_data['name'],
                    description=config_data['description'],
                    search_params=config_data['search_params'],
                    max_results=config_data['max_results']
                )
                
                logger.info(f"✅ Utworzono konfigurację: {config.name}")
                
            except Exception as e:
                logger.error(f"❌ Błąd tworzenia konfiguracji '{config_data['name']}': {e}")
    
    def create_test_user(self, email: str, name: str) -> User:
        """
        Utwórz użytkownika testowego
        
        Args:
            email: Email użytkownika
            name: Nazwa użytkownika
            
        Returns:
            Utworzony użytkownik
        """
        try:
            # Sprawdź czy użytkownik już istnieje
            existing_user = self.db_manager.get_user_by_email(email)
            if existing_user:
                logger.info(f"⚪ Użytkownik {email} już istnieje")
                return existing_user
            
            # Utwórz nowego użytkownika
            user = self.db_manager.create_user(email=email, name=name)
            logger.info(f"✅ Utworzono użytkownika testowego: {email}")
            
            return user
            
        except Exception as e:
            logger.error(f"❌ Błąd tworzenia użytkownika testowego: {e}")
            raise