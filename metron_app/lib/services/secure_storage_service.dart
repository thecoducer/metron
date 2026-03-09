import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );

  static const _apiKeyPrefix = 'api_key_';
  static const _apiSecretPrefix = 'api_secret_';

  /// Store a Zerodha API key for a given account
  static Future<void> saveApiKey(String accountName, String apiKey) async {
    await _storage.write(key: '$_apiKeyPrefix$accountName', value: apiKey);
  }

  /// Store a Zerodha API secret for a given account
  static Future<void> saveApiSecret(
      String accountName, String apiSecret) async {
    await _storage.write(
        key: '$_apiSecretPrefix$accountName', value: apiSecret);
  }

  /// Retrieve API key
  static Future<String?> getApiKey(String accountName) async {
    return _storage.read(key: '$_apiKeyPrefix$accountName');
  }

  /// Retrieve API secret
  static Future<String?> getApiSecret(String accountName) async {
    return _storage.read(key: '$_apiSecretPrefix$accountName');
  }

  /// Delete credentials for an account
  static Future<void> deleteAccount(String accountName) async {
    await _storage.delete(key: '$_apiKeyPrefix$accountName');
    await _storage.delete(key: '$_apiSecretPrefix$accountName');
  }

  /// List all stored account names
  static Future<List<String>> getStoredAccounts() async {
    final all = await _storage.readAll();
    final accounts = <String>{};
    for (final key in all.keys) {
      if (key.startsWith(_apiKeyPrefix)) {
        accounts.add(key.substring(_apiKeyPrefix.length));
      } else if (key.startsWith(_apiSecretPrefix)) {
        accounts.add(key.substring(_apiSecretPrefix.length));
      }
    }
    return accounts.toList()..sort();
  }

  /// Clear all stored credentials
  static Future<void> clearAll() async {
    await _storage.deleteAll();
  }

  /// Check if any accounts are configured
  static Future<bool> hasAccounts() async {
    final accounts = await getStoredAccounts();
    return accounts.isNotEmpty;
  }

  /// Store an arbitrary secret value
  static Future<void> saveSecret(String key, String value) async {
    await _storage.write(key: key, value: value);
  }

  /// Retrieve an arbitrary secret value
  static Future<String?> getSecret(String key) async {
    return _storage.read(key: key);
  }

  /// Check if running on a platform that supports secure storage
  static bool get isSupported =>
      defaultTargetPlatform == TargetPlatform.android ||
      defaultTargetPlatform == TargetPlatform.iOS ||
      kIsWeb;
}
