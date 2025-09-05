#!/usr/bin/env python3
"""
Serwis email Brevo dla CBOSA Bot
Obsługuje wysyłanie newsletterów przez API Brevo
"""

import os
import logging
import requests
import time
from typing import List, Optional, Union, Dict, Tuple
import base64
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class EmailRecipient:
    """Odbiorca emaila"""
    email: str
    name: str

@dataclass
class EmailContent:
    """Zawartość emaila"""
    subject: str
    html_content: str
    text_content: Optional[str] = None

@dataclass
class EmailSendResult:
    """Wynik wysłania emaila"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None

class BrevoEmailService:
    """Serwis wysyłania emaili przez Brevo API"""
    
    def __init__(self):
        self.api_key = os.getenv('BREVO_API_KEY')
        if not self.api_key:
            raise ValueError('BREVO_API_KEY nie jest ustawione')
        
        self.base_url = 'https://api.brevo.com/v3'
        self.headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        logger.info("✅ Serwis email Brevo zainicjalizowany")
    
    def _send_single_email(self, recipient: EmailRecipient, content: EmailContent,
                          sender_email: str, sender_name: str) -> EmailSendResult:
        """
        Wyślij pojedynczy email
        
        Args:
            recipient: Odbiorca
            content: Zawartość emaila
            sender_email: Email nadawcy
            sender_name: Nazwa nadawcy
            
        Returns:
            Wynik wysyłania
        """
        try:
            payload = {
                'sender': {
                    'email': sender_email,
                    'name': sender_name
                },
                'to': [
                    {
                        'email': recipient.email,
                        'name': recipient.name
                    }
                ],
                'subject': content.subject,
                'htmlContent': content.html_content
            }
            
            if content.text_content:
                payload['textContent'] = content.text_content
            
            response = requests.post(
                f'{self.base_url}/smtp/email',
                json=payload,
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code == 201:
                # Sukces
                response_data = response.json()
                message_id = response_data.get('messageId')
                
                logger.debug(f"✅ Email wysłany do {recipient.email}, messageId: {message_id}")
                return EmailSendResult(
                    success=True,
                    message_id=message_id
                )
            else:
                # Błąd
                error_msg = f"Błąd HTTP {response.status_code}: {response.text}"
                logger.error(f"❌ Błąd wysyłania do {recipient.email}: {error_msg}")
                return EmailSendResult(
                    success=False,
                    error=error_msg
                )
                
        except requests.exceptions.Timeout:
            error_msg = "Timeout podczas wysyłania emaila"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(
                success=False,
                error=error_msg
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"Błąd połączenia: {str(e)}"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(
                success=False,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd: {str(e)}"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(
                success=False,
                error=error_msg
            )
    
    def validate_email(self, email: str) -> bool:
        """
        Waliduj adres email
        
        Args:
            email: Adres email do walidacji
            
        Returns:
            True jeśli email jest prawidłowy
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def send_email(
        self,
        recipients: List[EmailRecipient],
        content: EmailContent,
        sender_email: str = 'newsletter.automatic.bot@gmail.com',
        sender_name: str = 'CBOSA Bot',
        attachments: Optional[List[Union[str, Tuple[str, bytes], Dict[str, str]]]] = None,
    ) -> List[EmailSendResult]:
        """
        Wyślij email do listy odbiorców.

        attachments:
            - lista ścieżek do plików (str), lub
            - lista krotek (name: str, data: bytes), lub
            - lista słowników w formacie Brevo: {"name": "...", "content": "<base64>"} lub {"name": "...", "url": "https://..."}
        """
        results = []
        # pre-normalizacja załączników do formatu akceptowanego przez Brevo
        normalized_attachments = self._normalize_attachments(attachments) if attachments else None

        batch_size = 50
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i + batch_size]
            for recipient in batch:
                result = self._send_single_email(
                    recipient, content, sender_email, sender_name, normalized_attachments
                )
                results.append(result)
                time.sleep(0.1)  # delikatne odciążenie limitów API

        successful = sum(1 for r in results if r.success)
        logger.info(f"📧 Wysłano {successful}/{len(results)} emaili pomyślnie")
        return results

    def _send_single_email(
        self,
        recipient: EmailRecipient,
        content: EmailContent,
        sender_email: str,
        sender_name: str,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> EmailSendResult:
        """
        Wyślij pojedynczy email (opcjonalnie z załącznikami).
        """
        try:
            payload = {
                'sender': {'email': sender_email, 'name': sender_name},
                'to': [{'email': recipient.email, 'name': recipient.name}],
                'subject': content.subject,
                'htmlContent': content.html_content,
            }
            if content.text_content:
                payload['textContent'] = content.text_content

            # Brevo SMTP API: klucz 'attachment' (lista obiektów z 'name' + 'content' (base64) lub 'url')
            if attachments:
                payload['attachment'] = attachments

            response = requests.post(
                f'{self.base_url}/smtp/email',
                json=payload,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 201:
                response_data = response.json()
                message_id = response_data.get('messageId')
                logger.debug(f"✅ Email wysłany do {recipient.email}, messageId: {message_id}")
                return EmailSendResult(success=True, message_id=message_id)

            error_msg = f"Błąd HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Błąd wysyłania do {recipient.email}: {error_msg}")
            return EmailSendResult(success=False, error=error_msg)

        except requests.exceptions.Timeout:
            error_msg = "Timeout podczas wysyłania emaila"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(success=False, error=error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Błąd połączenia: {str(e)}"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(success=False, error=error_msg)
        except Exception as e:
            error_msg = f"Nieoczekiwany błąd: {str(e)}"
            logger.error(f"❌ {error_msg} do {recipient.email}")
            return EmailSendResult(success=False, error=error_msg)

    def _normalize_attachments(
        self,
        attachments: List[Union[str, Tuple[str, bytes], Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """
        Znormalizuj różne formy wejścia do formatu akceptowanego przez Brevo:
        [{"name": "...", "content": "<base64>"}] lub [{"name": "...", "url": "https://..."}]
        """
        norm: List[Dict[str, str]] = []
        for att in attachments:
            # Ścieżka do pliku
            if isinstance(att, str):
                path = att
                name = os.path.basename(path)
                with open(path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                norm.append({"name": name, "content": b64})
                continue

            # Krotka (name, bytes)
            if isinstance(att, tuple) and len(att) == 2 and isinstance(att[0], str) and isinstance(att[1], (bytes, bytearray)):
                name, data = att
                b64 = base64.b64encode(bytes(data)).decode('ascii')
                norm.append({"name": name, "content": b64})
                continue

            # Już sformatowany słownik (content/url)
            if isinstance(att, dict):
                # walidacja podstawowa
                if 'name' in att and ('content' in att or 'url' in att):
                    norm.append(att)
                    continue

            raise ValueError("Nieprawidłowy format załącznika: "
                             "użyj ścieżki (str), krotki (name: str, data: bytes) lub dict z 'name' i 'content'/'url'.")

        return norm

    def send_bulk_newsletter(
        self,
        recipients: List[EmailRecipient],
        newsletter_html: str,
        config_name: str,
        attachments: Optional[List[Union[str, Tuple[str, bytes], Dict[str, str]]]] = None,
    ) -> List[EmailSendResult]:
        """
        Wyślij newsletter do wielu odbiorców (obsługa załączników).
        """
        from datetime import datetime
        current_date = datetime.now().strftime('%d.%m.%Y')
        subject = f"Biuletyn CBOSA: {config_name} - {current_date}"

        content = EmailContent(
            subject=subject,
            html_content=newsletter_html,
            text_content="Biuletyn dostępny jest w wersji HTML. Proszę włączyć wyświetlanie HTML w kliencie email."
        )

        logger.info(f"📤 Wysyłanie newslettera '{config_name}' do {len(recipients)} odbiorców")
        return self.send_email(recipients, content, attachments=attachments)
    
    def test_connection(self) -> bool:
        """
        Przetestuj połączenie z API Brevo
        
        Returns:
            True jeśli połączenie działa
        """
        try:
            response = requests.get(
                f'{self.base_url}/account',
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                account_info = response.json()
                logger.info(f"✅ Połączenie z Brevo działa. Konto: {account_info.get('email', 'Unknown')}")
                return True
            else:
                logger.error(f"❌ Błąd połączenia z Brevo: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Błąd testowania połączenia z Brevo: {e}")
            return False