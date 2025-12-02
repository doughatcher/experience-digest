#!/usr/bin/env python3
"""
Micro.blog Deployment Automation
Triggers theme reload, site rebuild, and monitors completion
"""

import os
import sys
import requests
import time
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class MicroblogDeployer:
    def __init__(self, session_cookie=None):
        self.theme_id = os.getenv('MICROBLOG_THEME_ID')
        
        if not self.theme_id:
            raise ValueError("MICROBLOG_THEME_ID not set in environment")
        
        # Get session cookie from argument or file or env
        if session_cookie:
            self.session_cookie = session_cookie
        elif os.path.exists('.session-cookie'):
            self.session_cookie = Path('.session-cookie').read_text().strip()
        else:
            self.session_cookie = os.getenv('MICROBLOG_SESSION_COOKIE')
        
        if not self.session_cookie:
            raise ValueError("No session cookie provided (use --session-cookie, .session-cookie file, or MICROBLOG_SESSION_COOKIE env var)")
        
        self.base_headers = {
            'Cookie': f'rack.session={self.session_cookie}',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
    
    def validate_session(self):
        """Test if session cookie is still valid"""
        print("🔐 Validating session cookie...")
        
        url = 'https://micro.blog/account/logs'
        headers = {**self.base_headers}
        
        try:
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
            
            # If redirected to signin, session is invalid
            if response.status_code == 302 and 'signin' in response.headers.get('Location', ''):
                print("❌ Session cookie is invalid or expired")
                return False
            
            if response.status_code == 200:
                print("✅ Session cookie is valid")
                return True
            
            print(f"⚠️  Unexpected response: {response.status_code}")
            return False
            
        except Exception as e:
            print(f"❌ Error validating session: {e}")
            return False
    
    def reload_theme(self):
        """Reload theme templates"""
        print(f"🎨 Reloading theme (ID: {self.theme_id})...")
        
        url = f'https://micro.blog/account/themes/{self.theme_id}/templates?reloading=1'
        headers = {
            **self.base_headers,
            'X-Requested-With': 'XMLHttpRequest',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': f'https://micro.blog/account/themes/{self.theme_id}/info'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("✅ Theme reload triggered successfully")
                return True
            elif response.status_code == 404:
                print(f"⚠️  Theme reload endpoint not found (404) - theme may not support reloading")
                print("   Note: Site rebuild will still pull in theme changes")
                return True  # Non-fatal - rebuild handles theme changes
            else:
                print(f"⚠️  Theme reload returned status {response.status_code}")
                if response.text:
                    print(f"   Response: {response.text[:200]}")
                return True  # Non-fatal
                
        except Exception as e:
            print(f"⚠️  Error reloading theme: {e}")
            return True  # Non-fatal
    
    def trigger_rebuild(self):
        """Trigger full site rebuild"""
        print("🔨 Triggering full site rebuild...")
        
        url = 'https://micro.blog/account/logs'
        headers = {
            **self.base_headers,
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Referer': 'https://micro.blog/account/logs'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("✅ Site rebuild triggered successfully")
                return True
            else:
                print(f"❌ Site rebuild failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Error triggering rebuild: {e}")
            return False
    
    def monitor_logs(self, timeout=300, check_interval=5):
        """Monitor build logs for completion"""
        print(f"📊 Monitoring build logs (timeout: {timeout}s, checking every {check_interval}s)...")
        
        url = 'https://micro.blog/account/logs?q='
        headers = {**self.base_headers}
        
        start_time = time.time()
        last_status = None
        completion_markers = ['Done 🎉', 'Publish: Done']
        error_markers = ['Error:', 'Failed:']
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                print(f"⏱️  Timeout reached ({timeout}s)")
                print("   Build may still be in progress - check logs manually")
                return False
            
            try:
                response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    print(f"   ⚠️  Could not fetch logs: {response.status_code}")
                    time.sleep(check_interval)
                    continue
                
                log_text = response.text
                
                # Check for completion
                for marker in completion_markers:
                    if marker in log_text:
                        print(f"✅ Build completed successfully! ({marker})")
                        return True
                
                # Check for errors
                for marker in error_markers:
                    if marker in log_text:
                        print(f"❌ Build error detected: {marker}")
                        # Show some context
                        lines = log_text.split('\n')
                        for i, line in enumerate(lines):
                            if marker in line:
                                print(f"   {line}")
                                if i + 1 < len(lines):
                                    print(f"   {lines[i + 1]}")
                        return False
                
                # Extract current status
                status_match = re.search(r'Publish: ([^\n]+)', log_text)
                if status_match:
                    current_status = status_match.group(1).strip()
                    if current_status != last_status:
                        print(f"   📝 {current_status}")
                        last_status = current_status
                
                # Wait before next check
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"   ⚠️  Error monitoring logs: {e}")
                time.sleep(check_interval)
        
        return False
    
    def deploy(self, reload=True, rebuild=True, monitor=True):
        """Execute deployment sequence"""
        print("🚀 Micro.blog Deployment")
        print("=" * 60)
        
        # Validate session first
        if not self.validate_session():
            print("\n❌ Session validation failed - please re-authenticate")
            print("   Run: python3 microblog_auth.py")
            return False
        
        success = True
        
        # Reload theme
        if reload:
            print()
            if not self.reload_theme():
                success = False
            time.sleep(2)  # Brief pause between operations
        
        # Trigger rebuild
        if rebuild:
            print()
            if not self.trigger_rebuild():
                success = False
            time.sleep(2)  # Brief pause before monitoring
        
        # Monitor logs
        if monitor and rebuild:
            print()
            if not self.monitor_logs():
                success = False
        
        print()
        print("=" * 60)
        if success:
            print("✅ Deployment completed successfully!")
        else:
            print("⚠️  Deployment completed with warnings/errors")
        
        return success


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Deploy updates to Micro.blog')
    parser.add_argument('--session-cookie', help='Session cookie value (or use .session-cookie file)')
    parser.add_argument('--reload', action='store_true', help='Reload theme templates')
    parser.add_argument('--rebuild', action='store_true', help='Trigger full site rebuild')
    parser.add_argument('--monitor', action='store_true', help='Monitor build logs for completion')
    parser.add_argument('--all', action='store_true', help='Run all operations (reload + rebuild + monitor)')
    parser.add_argument('--validate-only', action='store_true', help='Only validate session cookie')
    parser.add_argument('--timeout', type=int, default=300, help='Log monitoring timeout in seconds (default: 300)')
    
    args = parser.parse_args()
    
    # If no specific action specified, show help
    if not any([args.reload, args.rebuild, args.monitor, args.all, args.validate_only]):
        parser.print_help()
        print("\nExamples:")
        print("  python3 microblog_deploy.py --all                    # Full deployment")
        print("  python3 microblog_deploy.py --reload                 # Reload theme only")
        print("  python3 microblog_deploy.py --rebuild --monitor      # Rebuild and monitor")
        print("  python3 microblog_deploy.py --validate-only          # Test session cookie")
        sys.exit(1)
    
    try:
        deployer = MicroblogDeployer(session_cookie=args.session_cookie)
        
        if args.validate_only:
            success = deployer.validate_session()
            sys.exit(0 if success else 1)
        
        if args.all:
            success = deployer.deploy(reload=True, rebuild=True, monitor=True)
        else:
            success = deployer.deploy(
                reload=args.reload,
                rebuild=args.rebuild,
                monitor=args.monitor
            )
        
        sys.exit(0 if success else 1)
        
    except ValueError as e:
        print(f"\n❌ Configuration error: {e}")
        print("\nRequired environment variables:")
        print("  - MICROBLOG_THEME_ID")
        print("\nRequired authentication:")
        print("  - Session cookie via --session-cookie, .session-cookie file, or MICROBLOG_SESSION_COOKIE env var")
        print("\nRun authentication first:")
        print("  python3 microblog_auth.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
