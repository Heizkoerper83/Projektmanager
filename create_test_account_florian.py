#!/usr/bin/env python3
"""Create a local test account interactively."""

import getpass

from pmtool.collab_accounts import create_account, activate_account

try:
    email = input("E-Mail: ").strip()
    password = getpass.getpass("Passwort: ")

    # Create account
    account = create_account(
        email,
        password,
        role='editor'
    )
    print('✓ Account erstellt')
    print(f'  Email: {account["email"]}')
    print(f'  Role: {account["role"]}')
    print(f'  Enabled: {account["enabled"]}')
    print(f'  Activation Key: {account["activation_api_key"][:20]}...')
    
    # Activate account
    activation_key = account["activation_api_key"]
    activate_account(email, activation_key)
    print(f'\n✓ Account aktiviert')
    
except Exception as e:
    print(f'✗ Fehler: {e}')
    import traceback
    traceback.print_exc()
