#!/usr/bin/env python3
"""Create test account for florian.burtscher.at@icloud.com"""

from pmtool.collab_accounts import create_account, activate_account

try:
    # Create account
    account = create_account(
        'florian.burtscher.at@icloud.com',
        'TestPassword123!',
        role='editor'
    )
    print('✓ Account erstellt')
    print(f'  Email: {account["email"]}')
    print(f'  Role: {account["role"]}')
    print(f'  Enabled: {account["enabled"]}')
    print(f'  Activation Key: {account["activation_api_key"][:20]}...')
    
    # Activate account
    activation_key = account["activation_api_key"]
    activate_account('florian.burtscher.at@icloud.com', activation_key)
    print(f'\n✓ Account aktiviert')
    
except Exception as e:
    print(f'✗ Fehler: {e}')
    import traceback
    traceback.print_exc()
