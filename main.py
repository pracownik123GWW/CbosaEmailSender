#!/usr/bin/env python3
"""
CBOSA Bot - Główna aplikacja w Python
Automatyczny bot do analizy orzeczeń sądowych i wysyłki newsletterów
"""

import os
import logging
import schedule
import time
import threading
from dotenv import load_dotenv

from database import DatabaseManager
from brevo_service import BrevoEmailService
from cbosa_bot import CBOSABot

# Załaduj zmienne środowiskowe
load_dotenv()



# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class CBOSABotApplication:
    """Główna aplikacja CBOSA Bot"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.email_service = BrevoEmailService()
        self.bot = CBOSABot(self.db_manager, self.email_service)
        self.running = False
        
    def start_scheduler(self):
        """Uruchom harmonogram wykonywania zadań"""
        # Harmonogram: każdy poniedziałek o 7:00
        schedule.every().monday.at("07:00").do(self.run_scheduled_task)
        
        logger.info("⏰ Harmonogram uruchomiony - bot będzie działał w każdy poniedziałek o 7:00")
        
        # Wyświetl informacje o następnym uruchomieniu
        next_run = schedule.next_run()
        if next_run:
            logger.info(f"📅 Następne uruchomienie: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.running = True
        
        # Uruchom harmonogram w tle
        scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        scheduler_thread.start()
        
    def _scheduler_loop(self):
        """Pętla harmonogramu działająca w tle"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Sprawdzaj co minutę
    
    def run_scheduled_task(self):
        """Wykonaj zaplanowane zadanie bota"""
        logger.info("🤖 Rozpoczęcie zaplanowanego uruchomienia CBOSA Bot...")
        
        try:
            self.bot.execute_scheduled_run()
            logger.info("✅ Zaplanowane uruchomienie zakończone pomyślnie")
        except Exception as e:
            logger.error(f"❌ Błąd podczas zaplanowanego uruchomienia: {e}")
    
    def run_manual_test(self):
        """Uruchom test ręczny (do celów debugowania)"""
        logger.info("🚀 Ręczne uruchomienie testowe...")
        try:
            self.bot.execute_scheduled_run()
            logger.info("✅ Test ręczny zakończony pomyślnie")
        except Exception as e:
            logger.error(f"❌ Błąd podczas testu ręcznego: {e}")
    
    def stop(self):
        """Zatrzymaj aplikację"""
        logger.info("📴 Zatrzymywanie aplikacji...")
        self.running = False
        schedule.clear()

def main():
    """Główna funkcja aplikacji"""
    logger.info("🤖 CBOSA Bot uruchamia się...")
    
    # Sprawdź wymagane zmienne środowiskowe
    required_vars = ['DATABASE_URL', 'BREVO_API_KEY', 'OPENAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Brak wymaganych zmiennych środowiskowych: {', '.join(missing_vars)}")
        return
    
    app = CBOSABotApplication()
    
    try:
        logger.info("🗄️ Inicjalizacja bazy danych...")
        app.db_manager.init_database()
        
        # Uruchom harmonogram
        #app.start_scheduler()
        
        logger.info("✅ CBOSA Bot działa i jest zaplanowany")
        
        app.run_manual_test()
        app.stop()  # porządek, choć scheduler nie został uruchomiony
        logger.info("✅ Zakończono jednorazowe uruchomienie (tryb testowy)")
        return
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("📴 Otrzymano sygnał przerwania...")
        
    except Exception as e:
        logger.error(f"❌ Krytyczny błąd aplikacji: {e}")
    finally:
        app.stop()
        logger.info("📴 CBOSA Bot zatrzymany")

if __name__ == "__main__":
    main()