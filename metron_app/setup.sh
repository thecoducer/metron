#!/bin/bash
# Metron Flutter App - Setup Script
# Run this script once to initialize the Flutter project

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check Flutter
if ! command -v flutter &>/dev/null; then
  echo "❌ Flutter not found. Install it first:"
  echo "   brew install --cask flutter"
  echo "   or: https://docs.flutter.dev/get-started/install"
  exit 1
fi

echo "✅ Flutter found: $(flutter --version | head -1)"

# Generate platform directories (android, ios, web)
echo "🔧 Generating platform directories..."
flutter create --platforms android,ios,web --org com.metron .

# Install dependencies
echo "📦 Installing dependencies..."
flutter pub get

echo ""
echo "✅ Setup complete! You can now run:"
echo "   flutter run                  # Run on connected device"
echo "   flutter run -d chrome        # Run on web"
echo "   flutter build apk            # Build Android APK"
echo "   flutter build ios            # Build iOS"
