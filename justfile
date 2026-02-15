# Adobe Digest - Justfile
# Run tasks with: just <recipe-name>

# Default recipe - show available commands
default:
    @just --list

# Install Python dependencies
install:
    pip3 install -r content/requirements.txt

# Run the scraper to fetch new security bulletins
scrape:
    cd content && python3 scraper.py

# Clean scraped posts tracking file (will re-scrape all bulletins)
clean-posts:
    rm -f content/scraped_posts.json
    @echo "Cleared scraped posts tracking file"

# Build the Hugo site
build:
    hugo

# Run Hugo development server
serve:
    hugo serve --disableFastRender

# Run Hugo development server on all interfaces (for dev containers)
serve-all:
    hugo server -D --bind 0.0.0.0

# Clean Hugo build artifacts
clean-build:
    rm -rf public

# Full clean (build artifacts and scraper tracking)
clean-all: clean-build clean-posts
    @echo "Cleaned all generated files"

# Scrape and build in one command
refresh: scrape build
    @echo "Scraped new content and rebuilt site"

deps:
    pip3 install pyyaml

# Micro.blog Deployment Automation
# ================================

# Authenticate to Micro.blog via email and save session cookie
microblog-auth:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🔐 Authenticating to Micro.blog..."
    python3 .github/deploy/microblog_auth.py --output .session-cookie

# Validate existing session cookie
microblog-validate:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🔍 Validating session cookie..."
    python3 .github/deploy/microblog_deploy.py --validate-only

# Reload theme templates only
microblog-reload:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🎨 Reloading Micro.blog theme..."
    python3 .github/deploy/microblog_deploy.py --reload

# Trigger full site rebuild only
microblog-rebuild:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🔨 Triggering Micro.blog rebuild..."
    python3 .github/deploy/microblog_deploy.py --rebuild

# Monitor build logs for completion
microblog-monitor:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "📊 Monitoring build logs..."
    python3 .github/deploy/microblog_deploy.py --monitor

# Full deployment: authenticate, reload theme, rebuild, and monitor
microblog-deploy-all:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🚀 Running full Micro.blog deployment..."
    just microblog-auth
    echo ""
    python3 .github/deploy/microblog_deploy.py --all

# Quick deployment (assumes valid session exists): reload, rebuild, monitor
microblog-deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    echo "🚀 Deploying to Micro.blog (using existing session)..."
    python3 .github/deploy/microblog_deploy.py --all

# Micro.blog Backup Automation
# =============================

# Backup content from Micro.blog (export + download + extract)
backup:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    python3 .github/deploy/microblog_backup.py --all

# Backup and download only (no extraction)
backup-download:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    python3 .github/deploy/microblog_backup.py --export-only

# Extract content from existing backup ZIP
backup-extract ZIP_FILE:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{justfile_directory()}}"
    python3 .github/deploy/microblog_backup.py --extract-only {{ZIP_FILE}}