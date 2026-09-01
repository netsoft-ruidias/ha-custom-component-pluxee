#!/usr/bin/env python3
"""
Example script to test the Pluxee API client.

This script allows manual testing of the authentication flow and API calls.
"""
import asyncio
import os
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

from custom_components.pluxee.api import PluxeeAPI
from custom_components.pluxee.exceptions import AuthenticationError, PluxeeAPIError

load_dotenv()


async def main():
    """Test the API client."""
    print("=" * 60)
    print("Pluxee API Test Script")
    print("=" * 60)
    print()
    
    connector = aiohttp.TCPConnector(resolver=aiohttp.resolver.ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        api = PluxeeAPI(session)

        nif_input = input("Enter your NIF (or press Enter to use .env): ").strip()
        password_input = input("Enter your password (or press Enter to use .env): ").strip()

        nif = nif_input or os.getenv("PLUXEE_USERNAME", "")
        password = password_input or os.getenv("PLUXEE_PASSWORD", "")

        if not nif or not password:
            print("\n❌ Missing credentials!")
            print("Provide input values or set PLUXEE_USERNAME/PLUXEE_PASSWORD in .env")
            return

        print("\n🔐 Attempting authentication...")
        
        try:
            # Login
            success = await api.login(nif, password)
            if success:
                print("✅ Login successful!")
            else:
                print("❌ Login failed")
                return
            
            print("\n📊 Fetching data...")
            
            # Get card info
            card = await api.get_card()
            print("\n🆔 Card Information:")
            print(f"  ID: {card.id}")
            print(f"  Last digits: {card.pan_last_digits}")
            print(f"  Status: {card.status}")
            
            # Get balances
            balances = await api.get_balances()
            print(f"\n💰 Balances ({len(balances)}):")
            for balance in balances:
                print(f"  {balance.type.upper()}: {balance.balance:.2f} {balance.currency}")
            
            # Get transactions
            transactions = await api.get_movements(limit=10)
            print(f"\n📝 Recent Transactions ({len(transactions)}):")
            for tx in transactions:
                sign = "-" if tx.amount < 0 else "+"
                print(f"  {tx.date.strftime('%Y-%m-%d')}: {tx.description[:40]:40s} {sign}{abs(tx.amount):7.2f} {tx.currency}")
            
            print("\n✅ All tests completed successfully!")
            
        except AuthenticationError as e:
            print(f"\n❌ Authentication failed: {e}")
        except PluxeeAPIError as e:
            print(f"\n❌ API error: {e}")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
