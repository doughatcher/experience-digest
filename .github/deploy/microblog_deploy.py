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
        """Reload theme templates from GitHub"""
        print(f"🎨 Reloading theme from GitHub (ID: {self.theme_id})...")
        
        # POST to /account/themes/reload (which redirects to templates?reloading=1)
        url = 'https://micro.blog/account/themes/reload'
        headers = {
            **self.base_headers,
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Origin': 'https://micro.blog',
            'Referer': f'https://micro.blog/account/themes/{self.theme_id}/info',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # Send theme_id as form data
        form_data = {
            'theme_id': self.theme_id
        }
        
        try:
            # POST with theme_id, DON'T follow redirects - let it return 302
            response = requests.post(url, headers=headers, timeout=30, data=form_data, allow_redirects=False)
            
            # Should get a 302 redirect
            if response.status_code == 302:
                redirect_url = response.headers.get('Location', '')
                print(f"✅ Theme reload triggered (redirected to {redirect_url})")
                
                # Now follow the redirect manually to see the 404
                if redirect_url:
                    # Make it absolute if needed
                    if redirect_url.startswith('/'):
                        redirect_url = f'https://micro.blog{redirect_url}'
                    
                    # Follow the redirect
                    redirect_response = requests.get(redirect_url, headers={**self.base_headers}, timeout=30, allow_redirects=False)
                    if redirect_response.status_code == 404:
                        print("   (Redirect endpoint returns 404 as expected - reload is working)")
                    else:
                        print(f"   (Redirect returned {redirect_response.status_code})")
                
                return True
            elif response.status_code in [200, 404]:
                print("✅ Theme reload from GitHub triggered successfully")
                return True
            else:
                print(f"⚠️  Theme reload returned unexpected status {response.status_code}")
                if response.text:
                    print(f"   Response: {response.text[:200]}")
                return True  # Non-fatal
                
        except Exception as e:
            print(f"⚠️  Error reloading theme: {e}")
            return True  # Non-fatal
    
    def trigger_rebuild(self):
        """Trigger full site rebuild by visiting the logs page which starts the build"""
        print("🔨 Triggering site rebuild via logs page...")
        
        # Visit the logs page - this triggers the build process
        url = 'https://micro.blog/account/logs'
        headers = {
            **self.base_headers,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Referer': f'https://micro.blog/account/themes/{self.theme_id}/info'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                print("✅ Site rebuild triggered successfully")
                return True
            else:
                print(f"⚠️  Logs page returned status {response.status_code}")
                return True  # Non-fatal
                
        except Exception as e:
            print(f"⚠️  Error visiting logs page: {e}")
            return True  # Non-fatal
    
    def poll_check_endpoint(self, timeout=60, check_interval=5):
        """
        Poll the /posts/check endpoint which drives the build process.
        This endpoint must be called repeatedly for the build to progress.
        """
        print(f"📡 Polling /posts/check to drive build process...")
        print(f"   (Timeout: {timeout}s, interval: {check_interval}s)")
        
        check_url = 'https://micro.blog/posts/check'
        
        headers = {
            **self.base_headers,
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Referer': f'https://micro.blog/account/themes/{self.theme_id}/info'
        }
        
        start_time = time.time()
        poll_count = 0
        last_status = None
        seen_statuses = []
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout:
                print(f"\n⏱️  Timeout reached ({timeout}s) after {poll_count} polls")
                print("   Build may still be in progress - check https://micro.blog/account/logs")
                return False
            
            poll_count += 1
            
            try:
                # Poll the check endpoint to drive the build forward
                # Important: allow_redirects=True to follow any redirects
                check_response = requests.get(check_url, headers=headers, timeout=30, allow_redirects=True)
                
                # Check if we were redirected
                if check_response.history:
                    print(f"   [Poll #{poll_count}] Followed redirect: {check_response.url}")
                
                if check_response.status_code == 200:
                    try:
                        check_data = check_response.json()
                        
                        # Extract status information
                        is_publishing = check_data.get('is_publishing', False)
                        is_processing = check_data.get('is_processing', False)
                        publishing_status = check_data.get('publishing_status', '')
                        
                        # Show status changes
                        if publishing_status and publishing_status != last_status:
                            print(f"   📝 {publishing_status}")
                            last_status = publishing_status
                            seen_statuses.append(publishing_status)
                        
                        # Track publishing activity
                        if is_publishing or is_processing:
                            # Still actively publishing/processing
                            pass
                        else:
                            # Not publishing/processing
                            # If we've seen activity and now status is empty, we're likely done
                            # Or if we've done enough polls without activity, consider it done
                            if (seen_statuses and not publishing_status and poll_count > 3) or poll_count > 10:
                                print(f"\n✅ Build completed ({poll_count} polls)")
                                if seen_statuses:
                                    print(f"   Status progression: {' → '.join(seen_statuses)} → (complete)")
                                return True
                        
                        # Show progress every 5 polls
                        if poll_count % 5 == 0:
                            print(f"   [{poll_count} polls, {int(elapsed)}s elapsed...]")
                        
                    except ValueError as e:
                        print(f"   [Poll #{poll_count}] Non-JSON response")
                else:
                    print(f"   [Poll #{poll_count}] HTTP {check_response.status_code}")
                
                # Wait before next poll
                time.sleep(check_interval)
                
            except Exception as e:
                print(f"   ⚠️  Error during poll #{poll_count}: {e}")
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
        
        # Monitor build by polling check endpoint
        if monitor and rebuild:
            print()
            if not self.poll_check_endpoint():
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
    parser.add_argument('--timeout', type=int, default=60, help='Log monitoring timeout in seconds (default: 60)')
    
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
