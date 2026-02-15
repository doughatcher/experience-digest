#!/usr/bin/env python3
"""
Micro.blog Backup Automation
Exports theme from Micro.blog, downloads via email link, and extracts content locally
"""

import os
import sys
import imaplib
import email
import re
import requests
import time
import zipfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class MicroblogBackup:
    def __init__(self, session_cookie=None):
        self.site_id = os.getenv('MICROBLOG_SITE_ID')
        self.gmail_email = os.getenv('GMAIL_EMAIL')
        self.gmail_password = os.getenv('GMAIL_APP_PASSWORD')
        
        if not self.site_id:
            raise ValueError("MICROBLOG_SITE_ID not set in environment")
        if not self.gmail_email:
            raise ValueError("GMAIL_EMAIL not set in environment")
        if not self.gmail_password:
            raise ValueError("GMAIL_APP_PASSWORD not set in environment")
        
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
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        # Create backups directory if it doesn't exist
        self.backups_dir = Path('backups')
        self.backups_dir.mkdir(exist_ok=True)
    
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
    
    def trigger_export(self):
        """Trigger theme export from Micro.blog"""
        print(f"📦 Triggering theme export (site ID: {self.site_id})...")
        
        url = f'https://micro.blog/account/export/{self.site_id}'
        headers = {
            **self.base_headers,
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Referer': f'https://micro.blog/account/export/{self.site_id}',
            'Priority': 'u=0, i'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                export_time = datetime.utcnow()
                print(f"✅ Export triggered at {export_time.strftime('%H:%M:%S')} UTC")
                print("   Email notification will be sent when export is ready (typically 2-5 minutes)")
                return export_time
            else:
                print(f"❌ Failed to trigger export: {response.status_code}")
                if response.text:
                    print(f"   Response: {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"❌ Error triggering export: {e}")
            return None
    
    def connect_to_gmail(self):
        """Connect to Gmail via IMAP"""
        try:
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(self.gmail_email, self.gmail_password)
            return mail
        except Exception as e:
            print(f"❌ Error connecting to Gmail: {e}")
            return None
    
    def poll_email_for_export(self, export_time, max_retries=50, retry_interval=24):
        """Poll Gmail for export ready notification and extract download link
        
        Default timeout: 50 retries × 24s = 20 minutes
        This handles slow Micro.blog export processing during high load.
        """
        print(f"📧 Polling Gmail for export notification (up to {max_retries} retries, {retry_interval}s apart)...")
        print(f"   Total timeout: {max_retries * retry_interval // 60} minutes")
        
        # Search emails from 10 minutes before export request (in case of clock skew)
        search_start = export_time - timedelta(minutes=10)
        
        mail = self.connect_to_gmail()
        if not mail:
            return None
        
        try:
            for attempt in range(1, max_retries + 1):
                try:
                    # Wait before checking (except first attempt)
                    if attempt > 1:
                        print(f"   ⏳ Waiting {retry_interval}s before retry {attempt}/{max_retries}...")
                        time.sleep(retry_interval)
                    else:
                        # Small delay on first attempt to give email time to arrive
                        print(f"   ⏳ Waiting 15s for initial email delivery...")
                        time.sleep(15)
                    
                    # Select inbox
                    mail.select('INBOX')
                    
                    # Search for emails from help@micro.blog with export subject
                    search_criteria = '(FROM "help@micro.blog" SUBJECT "Export ready")'
                    result, data = mail.search(None, search_criteria)
                    
                    if result != 'OK':
                        print(f"   ⚠️  Search failed: {result}")
                        continue
                    
                    email_ids = data[0].split()
                    
                    if not email_ids:
                        print(f"   ℹ️  Attempt {attempt}/{max_retries}: No export emails found yet")
                        continue
                    
                    # Get last 50 emails (most recent first) to handle busy inboxes
                    email_ids = email_ids[-50:][::-1]
                    
                    print(f"   📬 Found {len(email_ids)} export emails, checking recent ones...")
                    
                    # Check each email for download link
                    for email_id in email_ids:
                        result, msg_data = mail.fetch(email_id, '(RFC822)')
                        if result != 'OK':
                            continue
                        
                        email_body = msg_data[0][1]
                        message = email.message_from_bytes(email_body)
                        
                        # Check email date to ensure it's recent (after our request)
                        email_date_str = message.get('Date', '')
                        try:
                            email_date = email.utils.parsedate_to_datetime(email_date_str)
                            # Make sure email is after our request (with 1 min buffer)
                            if email_date < search_start:
                                continue
                        except Exception as e:
                            # If date parsing fails, skip date check and process the email
                            pass
                        
                        subject = message.get('Subject', '')
                        print(f"   ✅ Found recent export email: {subject}")
                        
                        # Extract HTML content
                        html_content = None
                        if message.is_multipart():
                            for part in message.walk():
                                if part.get_content_type() == 'text/html':
                                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                        else:
                            if message.get_content_type() == 'text/html':
                                html_content = message.get_payload(decode=True).decode('utf-8', errors='ignore')
                        
                        if html_content:
                            # Extract S3 download URL from email
                            # Pattern: https://s3.amazonaws.com/micro.blog/archives/YYYY/MM/filename_hash.zip
                            match = re.search(r'https://s3\.amazonaws\.com/micro\.blog/archives/[^"]+\.zip', html_content)
                            if match:
                                download_url = match.group(0)
                                print(f"   🔗 Extracted download URL")
                                return download_url
                            else:
                                print(f"   ⚠️  No S3 download URL found in email")
                    
                    print(f"   ℹ️  Attempt {attempt}/{max_retries}: Export email not found in recent messages")
                    
                except Exception as e:
                    print(f"   ⚠️  Error during attempt {attempt}: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"❌ Failed to find export email after {max_retries} attempts")
            return None
            
        finally:
            # Close IMAP connection
            try:
                mail.close()
                mail.logout()
            except:
                pass
    
    def download_export_zip(self, download_url):
        """Download theme export ZIP from S3"""
        print(f"⬇️  Downloading theme export from S3...")
        
        # Extract filename from URL
        filename = download_url.split('/')[-1]
        output_path = self.backups_dir / filename
        
        try:
            response = requests.get(download_url, timeout=300, stream=True)
            
            if response.status_code == 200:
                # Get file size if available
                total_size = int(response.headers.get('content-length', 0))
                
                with open(output_path, 'wb') as f:
                    if total_size > 0:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            # Show progress every 10%
                            if total_size > 0 and downloaded % (total_size // 10) < 8192:
                                percent = (downloaded / total_size) * 100
                                print(f"   📥 {percent:.0f}% ({downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB)")
                    else:
                        # No content-length header, just download
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                
                file_size = output_path.stat().st_size / 1024 / 1024
                print(f"✅ Theme export downloaded: {output_path}")
                print(f"   Size: {file_size:.2f}MB")
                return output_path
            else:
                print(f"❌ Failed to download export: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Error downloading export: {e}")
            return None
    
    def backup_existing_content(self):
        """Create timestamped backup of current content directory"""
        content_dir = Path('content')
        
        if not content_dir.exists():
            print("ℹ️  No existing content directory to backup")
            return None
        
        print("💾 Backing up existing content directory...")
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_filename = f'content-backup-{timestamp}.zip'
        backup_path = self.backups_dir / backup_filename
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                file_count = 0
                for file_path in content_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(content_dir.parent)
                        zipf.write(file_path, arcname)
                        file_count += 1
            
            file_size = backup_path.stat().st_size / 1024
            print(f"✅ Content backup created: {backup_path}")
            print(f"   Files: {file_count}, Size: {file_size:.2f}KB")
            return backup_path
            
        except Exception as e:
            print(f"⚠️  Error creating content backup: {e}")
            return None
    
    def extract_content(self, zip_path, extract_all=True):
        """Extract content from theme export ZIP to workspace"""
        print(f"📂 Extracting content from theme export...")
        
        if not zip_path.exists():
            print(f"❌ ZIP file not found: {zip_path}")
            return False
        
        try:
            # Create temporary extraction directory
            temp_dir = self.backups_dir / 'temp_extract'
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(exist_ok=True)
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            print(f"   ✅ Theme archive extracted to temporary directory")
            
            # Check if content is at root level or in a subdirectory
            # Try to find content/ directory to determine structure
            content_test = temp_dir / 'content'
            if content_test.exists():
                # Content is at root level
                theme_dir = temp_dir
                print(f"   📁 Theme structure: root level")
            else:
                # Find the theme directory (should be single directory in zip)
                theme_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
                if not theme_dirs:
                    print(f"❌ No theme directory found in ZIP")
                    shutil.rmtree(temp_dir)
                    return False
                
                theme_dir = theme_dirs[0]
                print(f"   📁 Theme directory: {theme_dir.name}")
            
            # Directories to extract
            if extract_all:
                dirs_to_extract = ['content', 'data', 'layouts', 'static']
            else:
                dirs_to_extract = ['content', 'data']
            
            workspace_root = Path.cwd()
            extracted_count = 0
            
            for dir_name in dirs_to_extract:
                source_dir = theme_dir / dir_name
                if not source_dir.exists():
                    print(f"   ⚠️  {dir_name}/ not found in theme export")
                    continue
                
                dest_dir = workspace_root / dir_name
                
                # Remove existing directory if it exists
                if dest_dir.exists():
                    print(f"   🗑️  Removing existing {dir_name}/")
                    shutil.rmtree(dest_dir)
                
                # Copy directory from theme export
                print(f"   📋 Copying {dir_name}/ to workspace...")
                shutil.copytree(source_dir, dest_dir)
                
                # Count files
                file_count = sum(1 for _ in dest_dir.rglob('*') if _.is_file())
                print(f"   ✅ {dir_name}/ extracted ({file_count} files)")
                extracted_count += 1
            
            # Clean up temporary directory
            shutil.rmtree(temp_dir)
            
            print(f"✅ Content extraction complete ({extracted_count} directories)")
            return True
            
        except Exception as e:
            print(f"❌ Error extracting content: {e}")
            import traceback
            traceback.print_exc()
            # Clean up temp directory on error
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            return False
    
    def backup(self, export=True, download=True, extract=True, backup_existing=True, max_retries=50, retry_interval=24):
        """Execute full backup sequence"""
        print("🚀 Micro.blog Backup")
        print("=" * 60)
        
        # Validate session first
        if not self.validate_session():
            print("\n❌ Session validation failed - please re-authenticate")
            print("   Run: python3 microblog_auth.py")
            return False
        
        success = True
        export_zip_path = None
        
        # Step 1: Trigger export
        if export:
            print()
            export_time = self.trigger_export()
            if not export_time:
                success = False
                export = False  # Skip dependent steps
            
            # Step 2: Poll email for download link
            if download and export_time:
                print()
                download_url = self.poll_email_for_export(export_time, max_retries=max_retries, retry_interval=retry_interval)
                if not download_url:
                    success = False
                    download = False
                
                # Step 3: Download export
                if download_url:
                    print()
                    export_zip_path = self.download_export_zip(download_url)
                    if not export_zip_path:
                        success = False
                        extract = False
        
        # Step 4: Backup existing content
        if backup_existing and extract:
            print()
            self.backup_existing_content()
        
        # Step 5: Extract content
        if extract and export_zip_path:
            print()
            if not self.extract_content(export_zip_path):
                success = False
        
        print()
        print("=" * 60)
        if success:
            print("✅ Backup completed successfully!")
            if export_zip_path:
                print(f"   Theme archive: {export_zip_path}")
        else:
            print("⚠️  Backup completed with warnings/errors")
        
        return success


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Backup content from Micro.blog')
    parser.add_argument('--session-cookie', help='Session cookie value (or use .session-cookie file)')
    parser.add_argument('--export-only', action='store_true', help='Only trigger export and download (no extraction)')
    parser.add_argument('--extract-only', help='Extract content from existing ZIP file')
    parser.add_argument('--all', action='store_true', help='Run full backup (export + download + extract)')
    parser.add_argument('--no-backup', action='store_true', help='Skip backing up existing content before extraction')
    parser.add_argument('--max-retries', type=int, default=50, help='Max retries for email polling (default: 50)')
    parser.add_argument('--retry-interval', type=int, default=24, help='Seconds between retries (default: 24)')

    args = parser.parse_args()
    
    # If no specific action specified, show help
    if not any([args.export_only, args.extract_only, args.all]):
        parser.print_help()
        print("\nExamples:")
        print("  python3 microblog_backup.py --all                    # Full backup with extraction")
        print("  python3 microblog_backup.py --export-only            # Export and download only")
        print("  python3 microblog_backup.py --extract-only backup.zip  # Extract from existing ZIP")
        sys.exit(1)
    
    try:
        # Handle extract-only mode (no session cookie needed)
        if args.extract_only:
            # Create minimal backup instance just for extraction
            backup = MicroblogBackup(session_cookie='dummy')
            zip_path = Path(args.extract_only)
            if not zip_path.exists():
                # Try in backups directory
                zip_path = Path('backups') / args.extract_only
            
            if not zip_path.exists():
                print(f"❌ ZIP file not found: {args.extract_only}")
                sys.exit(1)
            
            print("🚀 Micro.blog Backup - Extract Only")
            print("=" * 60)
            
            if not args.no_backup:
                print()
                backup.backup_existing_content()
            
            print()
            success = backup.extract_content(zip_path)
            print()
            print("=" * 60)
            if success:
                print("✅ Extraction completed successfully!")
            else:
                print("❌ Extraction failed")
            
            sys.exit(0 if success else 1)
        
        # Normal backup modes (need session cookie)
        backup = MicroblogBackup(session_cookie=args.session_cookie)
        
        if args.all:
            success = backup.backup(
                export=True,
                download=True,
                extract=True,
                backup_existing=not args.no_backup,
                max_retries=args.max_retries,
                retry_interval=args.retry_interval
            )
        elif args.export_only:
            success = backup.backup(
                export=True,
                download=True,
                extract=False,
                backup_existing=False,
                max_retries=args.max_retries,
                retry_interval=args.retry_interval
            )
        else:
            success = True
        
        sys.exit(0 if success else 1)
        
    except ValueError as e:
        print(f"\n❌ Configuration error: {e}")
        print("\nRequired environment variables:")
        print("  - MICROBLOG_SITE_ID")
        print("  - GMAIL_EMAIL")
        print("  - GMAIL_APP_PASSWORD")
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
