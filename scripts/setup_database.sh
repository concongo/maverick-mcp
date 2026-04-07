#!/bin/bash
"""
Complete database setup script for MaverickMCP.

This script runs the migration and seeding process to set up a complete
working database for the MaverickMCP application.
"""

set -e  # Exit on any error

echo "🚀 MaverickMCP Database Setup"
echo "=============================="

# Change to project root directory
cd "$(dirname "$0")/.."

# Check if virtual environment is activated
if [[ -z "${VIRTUAL_ENV}" ]] && [[ ! -d ".venv" ]]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Consider running: python -m venv .venv && source .venv/bin/activate"
    echo ""
fi

# Check for required environment variables
if [[ -z "${TIINGO_API_KEY}" ]]; then
    echo "❌ TIINGO_API_KEY environment variable is required!"
    echo ""
    echo "To get started:"
    echo "1. Sign up for a free account at https://tiingo.com"
    echo "2. Get your API key from the dashboard"
    echo "3. Add it to your .env file: TIINGO_API_KEY=your_api_key_here"
    echo "4. Or export it: export TIINGO_API_KEY=your_api_key_here"
    echo ""
    exit 1
fi

echo "📋 Environment Check:"
echo "   TIINGO_API_KEY: ✅ Set"
if [[ -n "${DATABASE_URL}" ]]; then
    echo "   DATABASE_URL: ${DATABASE_URL}"
else
    echo "   DATABASE_URL: sqlite:///./maverick_mcp.db (default)"
fi
echo ""

echo "1️⃣ Running database migration..."
echo "--------------------------------"
python scripts/migrate_db.py
if [ $? -eq 0 ]; then
    echo "✅ Migration completed successfully"
else
    echo "❌ Migration failed"
    exit 1
fi
echo ""

echo "2️⃣ Running database seeding..."
echo "------------------------------"
python scripts/seed_db.py
if [ $? -eq 0 ]; then
    echo "✅ Seeding completed successfully"
else
    echo "❌ Seeding failed"
    exit 1
fi
echo ""

echo "🎉 Database setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Run the MCP server: make dev"
echo "2. Connect with Claude Desktop using mcp-remote"
echo "3. Test with: 'Show me technical analysis for AAPL'"
echo ""
echo "Available screening tools:"
echo "- get_maverick_recommendations (bullish momentum stocks)"
echo "- get_maverick_bear_recommendations (bearish setups)"
echo "- get_trending_breakout_recommendations (breakout candidates)"
