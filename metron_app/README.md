# Metron Flutter App

A modern portfolio tracker built with Flutter, targeting Android, iOS, and Web.

## Quick Start

### 1. Install Flutter SDK (if not installed)

```bash
brew install --cask flutter
```

Or follow: https://docs.flutter.dev/get-started/install/macos

### 2. Initialize the project

```bash
cd metron_app
./setup.sh
```

This generates the Android, iOS, and Web platform directories and installs dependencies.

### 3. Run the app

```bash
# Android (connect device or start emulator)
flutter run

# Web
flutter run -d chrome

# Build APK
flutter build apk --release
```

## Architecture

```
lib/
├── main.dart                 # Entry point
├── app.dart                  # App shell with navigation
├── models/                   # Data models (stocks, MFs, SIPs, gold, FDs, PF)
│   ├── stock_holding.dart
│   ├── mutual_fund.dart
│   ├── sip.dart
│   ├── physical_gold.dart
│   ├── fixed_deposit.dart
│   ├── provident_fund.dart
│   └── market_index.dart
├── services/
│   ├── mock_data_service.dart       # Mock portfolio data
│   ├── portfolio_provider.dart      # State management (Provider)
│   └── secure_storage_service.dart  # Encrypted credential storage
├── screens/
│   ├── dashboard_screen.dart   # Main overview with summary cards + charts
│   ├── holdings_screen.dart    # Stocks, Mutual Funds, SIPs (tabbed)
│   ├── assets_screen.dart      # Gold, FDs, Provident Fund (tabbed)
│   └── settings_screen.dart    # Broker account management
├── widgets/
│   ├── market_ticker.dart      # Scrolling market indices bar
│   ├── summary_card.dart       # Asset summary cards
│   ├── section_header.dart     # Section titles with "View All"
│   ├── holding_list_tile.dart  # Individual holding row
│   ├── portfolio_chart.dart    # Donut chart + sparklines
│   └── portfolio_header.dart   # Total portfolio value header
├── theme/
│   ├── app_theme.dart          # Dark theme configuration
│   └── app_colors.dart         # Color palette
└── utils/
    └── formatters.dart         # Currency, number, date formatting
```

## Features

- **4 screens**: Dashboard, Holdings, Assets, Settings
- **6 asset classes**: Stocks, Mutual Funds, SIPs, Physical Gold, Fixed Deposits, Provident Fund
- **Responsive**: Bottom nav on mobile, side rail on wide screens
- **Dark theme**: GitHub-inspired dark palette
- **Secure storage**: API credentials stored encrypted on device
- **Mock data**: Pre-loaded realistic Indian market data for testing

## Security

API keys and secrets are stored using `flutter_secure_storage`:
- **Android**: EncryptedSharedPreferences (AES-256)
- **iOS**: Keychain with first_unlock accessibility
- **Web**: (Limited — localStorage with best-effort encryption)
