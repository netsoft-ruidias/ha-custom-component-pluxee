"""Pluxee API Client with HTML scraping."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any
from datetime import datetime, timezone

import aiohttp
from aiohttp import ClientSession
from bs4 import BeautifulSoup

from .exceptions import AuthenticationError, PluxeeAPIError
from .interfaces import Card, Balance, Transaction
from .const import API_LOGIN_URL, API_CONSUMER_URL

_LOGGER = logging.getLogger(__name__)


class PluxeeAPI:
    """Client for interacting with the Pluxee portal via HTML scraping."""

    def __init__(self, session: ClientSession):
        """Initialize the API client."""
        self._session = session
        self._base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._authenticated = False
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

    @property
    def refresh_token(self) -> str | None:
        """Return the current auth context token from cookies."""
        return self._refresh_token

    @property
    def token_expires_at(self) -> datetime | None:
        """Return the UTC expiration timestamp for the current auth token."""
        return self._token_expires_at

    def is_token_expiring_soon(self, buffer_seconds: int = 300) -> bool:
        """Return True when auth token is missing or close to expiry."""
        if not self._refresh_token or not self._token_expires_at:
            return True
        now_utc = datetime.now(timezone.utc)
        remaining = (self._token_expires_at - now_utc).total_seconds()
        return remaining <= buffer_seconds

    def _extract_auth_cookie_token(self) -> str | None:
        """Extract AUTH_BEARER_CONTEXT token from current cookie jar."""
        for cookie in self._session.cookie_jar:
            if cookie.key == "AUTH_BEARER_CONTEXT":
                return cookie.value
        return None

    @staticmethod
    def _decode_jwt_exp(token: str) -> datetime | None:
        """Decode JWT payload and return exp as UTC datetime if available."""
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload_segment = parts[1]
        payload_segment += "=" * (-len(payload_segment) % 4)
        try:
            payload_bytes = base64.urlsafe_b64decode(payload_segment.encode("ascii"))
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None

        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return None
        return datetime.fromtimestamp(exp, timezone.utc)

    def _update_auth_context_from_cookies(self) -> None:
        """Refresh in-memory auth context based on current cookies."""
        token = self._extract_auth_cookie_token()
        self._refresh_token = token
        self._token_expires_at = self._decode_jwt_exp(token) if token else None

    async def login(self, nif: str, password: str) -> bool:
        """
        Authenticate with Pluxee portal.
        
        Args:
            nif: Tax identification number (9 digits)
            password: Account password
            
        Returns:
            True if authentication successful
            
        Raises:
            AuthenticationError: Invalid credentials
            PluxeeAPIError: Other errors
        """
        _LOGGER.debug("Attempting login for NIF: %s", nif)
        
        try:
            # Step 1: GET login page to obtain any CSRF tokens if needed
            async with self._session.get(
                API_LOGIN_URL,
                headers=self._base_headers,
                allow_redirects=True
            ) as resp:
                if resp.status != 200:
                    raise PluxeeAPIError(f"Failed to load login page: {resp.status}")
                
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for form and any hidden fields (CSRF tokens, etc.)
                form = soup.find('form')
                form_data = {}
                
                if form:
                    # Collect all hidden input fields
                    for hidden in form.find_all('input', type='hidden'):
                        name = hidden.get('name')
                        value = hidden.get('value', '')
                        if name:
                            form_data[name] = value
                
                # Add credentials to form data
                # Field names from actual form: nif and pass
                form_data['nif'] = nif
                form_data['pass'] = password
                
            # Step 2: POST credentials to login_processing.php
            login_action_url = f"{API_LOGIN_URL}login_processing.php"
            async with self._session.post(
                login_action_url,
                data=form_data,
                headers={
                    **self._base_headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                allow_redirects=False  # Don't follow redirects, we'll handle manually
            ) as resp:
                if resp.status != 200:
                    raise PluxeeAPIError(f"Login request failed: {resp.status}")
                
                # login_processing.php returns JSON with UTF-8 BOM: {"sucesso":true,"mensagem":"","local":"https://..."}
                try:
                    text = await resp.text()
                    # Remove UTF-8 BOM if present
                    if text.startswith('\ufeff'):
                        text = text[1:]

                    result = json.loads(text)
                except Exception as err:
                    # If not JSON, log error
                    _LOGGER.error("Failed to parse login response: %s", err)
                    raise PluxeeAPIError("Unexpected response from login endpoint") from err
                
                # Check if login was successful
                if not result.get("sucesso"):
                    mensagem = result.get("mensagem", "Unknown error")
                    _LOGGER.warning("Login failed: %s", mensagem)
                    raise AuthenticationError(f"Invalid NIF or password: {mensagem}")
                
                # Get redirect URL from response
                redirect_url = result.get("local", "")
                if not redirect_url or "consumidores.pluxee.pt" not in redirect_url:
                    _LOGGER.error("No valid redirect URL in response: %s", result)
                    raise PluxeeAPIError("No redirect URL after login")
                
                _LOGGER.debug("Login successful, redirect to: %s", redirect_url)
                
            # Step 3: Visit the consumer portal to establish session
            async with self._session.get(
                redirect_url,
                headers=self._base_headers,
                allow_redirects=True
            ) as resp:
                final_url = str(resp.url)
                
                # Check if we were redirected to the consumer portal
                if API_CONSUMER_URL in final_url or "consumidores.pluxee.pt" in final_url:
                    _LOGGER.debug("Login successful - redirected to %s", final_url)
                    self._authenticated = True
                    self._update_auth_context_from_cookies()
                    return True
                
                # Check if we're still on the login page (authentication failed)
                if "portal.admin.pluxee.pt" in final_url:
                    _LOGGER.warning("Login failed - still on login page")
                    raise AuthenticationError("Invalid NIF or password")
                
                # Check response for error messages
                html = await resp.text()
                if "erro" in html.lower() or "inválid" in html.lower():
                    raise AuthenticationError("Invalid NIF or password")
                
                # If we got here, something unexpected happened
                _LOGGER.error("Unexpected response after login attempt")
                raise PluxeeAPIError("Unexpected response from login")
                
        except AuthenticationError:
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error during login: %s", err)
            raise PluxeeAPIError(f"Network error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error during login: %s", err)
            raise PluxeeAPIError(f"Login failed: {err}") from err

    async def get_card_data(self) -> dict[str, Any]:
        """
        Get card data by scraping the main page HTML.
        
        Returns:
            Dict with card, balance, and transactions
            
        Raises:
            PluxeeAPIError: If not authenticated or scraping fails
        """
        if not self._authenticated:
            raise AuthenticationError("Not authenticated - call login() first")
        
        _LOGGER.debug("Fetching card data from %s", API_CONSUMER_URL)
        
        try:
            async with self._session.get(
                API_CONSUMER_URL,
                headers=self._base_headers,
                allow_redirects=True
            ) as resp:
                # Check if we were redirected back to login (session expired)
                if "portal.admin.pluxee.pt" in str(resp.url):
                    self._authenticated = False
                    self._refresh_token = None
                    self._token_expires_at = None
                    raise AuthenticationError("Session expired - need to re-authenticate")
                
                if resp.status != 200:
                    raise PluxeeAPIError(f"Failed to fetch data: {resp.status}")
                
                html = await resp.text()
                return self._parse_html(html)
                
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error fetching data: %s", err)
            raise PluxeeAPIError(f"Network error: {err}") from err

    def _parse_html(self, html: str) -> dict[str, Any]:
        """Parse HTML and extract all data."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find main content
        main = soup.find('main')
        if not main:
            raise PluxeeAPIError("Could not find main content in page")
        
        data = {}
        
        # Extract balance - look for h1 with class "card-heading"
        balance_h1 = main.find('h1', class_='card-heading')
        if balance_h1:
            text = balance_h1.get_text(strip=True)
            # Text is like "115,06" (comma as decimal separator, no € symbol)
            balance_str = text.replace(',', '.').replace('\xa0', '').replace(' ', '')
            try:
                data['balance'] = float(balance_str)
            except ValueError:
                _LOGGER.warning("Could not parse balance from: %s", text)
                data['balance'] = 0.0
        
        # Extract card information from paragraphs with specific classes
        # Card info is in <p class="card-info2">Cartão Nº: ************0773<br> ID Card <span id="card_id">62797511</span></p>
        card_info = main.find('p', class_='card-info2')
        if card_info:
            text = card_info.get_text()
            
            # Card number - look for pattern like ************0773
            card_match = re.search(r'\*+(\d+)', text)
            if card_match:
                data['card_number'] = '************' + card_match.group(1)
            
            # Card ID - from span or text
            id_span = card_info.find('span', id='card_id')
            if id_span:
                data['card_id'] = id_span.get_text(strip=True)
        
        # Available date - from <p class="card-info1">Saldo disponível em 01-09-2026</p>
        date_info = main.find('p', class_='card-info1')
        if date_info:
            text = date_info.get_text(strip=True)
            match = re.search(r'(\d{2}-\d{2}-\d{4})', text)
            if match:
                data['available_date'] = match.group(1)
        
        # Extract transactions from table
        transactions = []
        table = main.find('table')
        if table:
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        # Date - in <p class="dateFormatDesk">DD/MM/YYYY</p>
                        date_p = cells[0].find('p', class_='dateFormatDesk')
                        if date_p:
                            date_str = date_p.get_text(strip=True)
                        else:
                            date_str = cells[0].get_text(strip=True)
                        
                        # Description - in <p class="text-left">
                        desc_p = cells[1].find('p', class_='text-left')
                        if desc_p:
                            # Remove img elements from description
                            for img in desc_p.find_all('img'):
                                img.decompose()
                            description = desc_p.get_text(strip=True)
                        else:
                            description = cells[1].get_text(strip=True)
                        
                        # Amount - in <span class="saldo_p"> or <span class="saldo_n">
                        amount_span = cells[2].find('span', class_=lambda x: x and ('saldo_p' in x or 'saldo_n' in x))
                        if amount_span:
                            amount_str = amount_span.get_text(strip=True)
                        else:
                            amount_str = cells[2].get_text(strip=True)
                        
                        transactions.append({
                            'date': date_str,
                            'description': description,
                            'amount': amount_str,
                        })
        
        data['transactions'] = transactions
        
        _LOGGER.debug("Extracted data: balance=%s, card=%s, %d transactions",
                     data.get('balance'), data.get('card_number'), len(transactions))
        
        return data

    async def get_card(self) -> Card:
        """
        Get card information.
        
        Returns:
            Card object
        """
        data = await self.get_card_data()
        
        # Build card data dict
        card_data = {
            'id': data.get('card_id', ''),
            'pan_last_digits': data.get('card_number', '').replace('*', '').strip(),
            'holder_name': '',  # Not available in HTML
            'holder_company_name': '',  # Not available in HTML
            'status': 'active',  # Assume active if we can see it
            'activated_at': None,
            'expiration_date': None,
        }
        
        return Card(card_data)

    async def get_balances(self) -> list[Balance]:
        """
        Get balance information.
        
        Returns:
            List with single Balance object
        """
        data = await self.get_card_data()
        
        balance_data = {
            'id': data.get('card_id', ''),
            'type': 'meal',  # Pluxee is meal card
            'balance': {
                'amount': int(data.get('balance', 0) * 100),  # Convert to cents
                'currency': 'EUR',
            },
        }
        
        return [Balance(balance_data)]

    async def get_movements(self, limit: int = 20) -> list[Transaction]:
        """
        Get transaction history.
        
        Args:
            limit: Maximum number of transactions
            
        Returns:
            List of Transaction objects
        """
        data = await self.get_card_data()
        transactions = []
        
        for tx in data.get('transactions', [])[:limit]:
            # Parse date - format is "DD/MM/YYYY"
            date_str = tx['date']
            try:
                if '/' in date_str:
                    dt = datetime.strptime(date_str, '%d/%m/%Y')
                    executed_at = dt.isoformat()
                else:
                    executed_at = datetime.now().isoformat()
            except ValueError:
                executed_at = datetime.now().isoformat()
            
            # Parse amount
            amount_str = tx['amount'].replace('€', '').replace(',', '.').strip()
            try:
                amount_float = float(amount_str)
                is_debit = False
                if amount_float < 0:
                    is_debit = True
                    amount_float = abs(amount_float)
            except ValueError:
                amount_float = 0.0
                is_debit = False
            
            tx_data = {
                'executed_at': executed_at,
                'description': tx['description'],
                'amount': {
                    'amount': int(amount_float * 100),
                    'currency': 'EUR',
                },
                'is_debit': is_debit,
            }
            
            transactions.append(Transaction(tx_data))
        
        return transactions
