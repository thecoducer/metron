import 'package:flutter/material.dart';
import '../services/secure_storage_service.dart';
import '../theme/app_colors.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  List<String> _accounts = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  Future<void> _loadAccounts() async {
    final accounts = await SecureStorageService.getStoredAccounts();
    setState(() {
      _accounts = accounts;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ── Profile Placeholder ──
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Row(
            children: [
              CircleAvatar(
                radius: 28,
                backgroundColor: AppColors.primary.withAlpha(40),
                child: const Text(
                  'M',
                  style: TextStyle(
                    color: AppColors.primary,
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: 16),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Metron User',
                      style: TextStyle(
                        color: AppColors.textPrimary,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 4),
                    Text(
                      'Portfolio Tracker',
                      style: TextStyle(
                        color: AppColors.textMuted,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Zerodha Accounts ──
        _buildSectionTitle('Broker Accounts'),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Column(
            children: [
              if (_loading)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Center(
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                )
              else if (_accounts.isEmpty)
                _buildEmptyAccountPrompt()
              else
                ..._accounts.map((a) => _buildAccountTile(a)),
              _buildAddAccountButton(),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── App Settings ──
        _buildSectionTitle('App'),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Column(
            children: [
              _buildSettingsTile(
                icon: Icons.palette_outlined,
                title: 'Theme',
                subtitle: 'Dark mode',
                trailing: const Icon(Icons.brightness_4_rounded,
                    color: AppColors.textMuted, size: 20),
              ),
              const Divider(height: 1, indent: 56, endIndent: 12),
              _buildSettingsTile(
                icon: Icons.notifications_outlined,
                title: 'Notifications',
                subtitle: 'Market alerts & reminders',
              ),
              const Divider(height: 1, indent: 56, endIndent: 12),
              _buildSettingsTile(
                icon: Icons.info_outline_rounded,
                title: 'About Metron',
                subtitle: 'v1.0.0',
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // ── Danger Zone ──
        _buildSectionTitle('Data'),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardDark,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.loss.withAlpha(25)),
          ),
          child: _buildSettingsTile(
            icon: Icons.delete_outline_rounded,
            iconColor: AppColors.loss,
            title: 'Clear All Data',
            subtitle: 'Remove stored credentials & cache',
            onTap: () => _showClearDataDialog(context),
          ),
        ),
        const SizedBox(height: 40),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title.toUpperCase(),
      style: const TextStyle(
        color: AppColors.textMuted,
        fontSize: 12,
        fontWeight: FontWeight.w600,
        letterSpacing: 1.2,
      ),
    );
  }

  Widget _buildEmptyAccountPrompt() {
    return const Padding(
      padding: EdgeInsets.all(20),
      child: Column(
        children: [
          Icon(Icons.link_off_rounded, color: AppColors.textMuted, size: 32),
          SizedBox(height: 8),
          Text(
            'No broker accounts connected',
            style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
          ),
          SizedBox(height: 4),
          Text(
            'Add your Zerodha API credentials to get started',
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildAccountTile(String accountName) {
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: AppColors.profit.withAlpha(20),
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Center(
          child: Icon(Icons.check_circle_rounded,
              color: AppColors.profit, size: 20),
        ),
      ),
      title: Text(
        accountName,
        style: const TextStyle(
          color: AppColors.textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
      subtitle: const Text(
        'Zerodha KiteConnect',
        style: TextStyle(color: AppColors.textMuted, fontSize: 12),
      ),
      trailing: IconButton(
        icon: const Icon(Icons.delete_outline_rounded,
            color: AppColors.loss, size: 20),
        onPressed: () => _confirmDeleteAccount(accountName),
      ),
    );
  }

  Widget _buildAddAccountButton() {
    return InkWell(
      onTap: () => _showAddAccountDialog(context),
      borderRadius: const BorderRadius.only(
        bottomLeft: Radius.circular(16),
        bottomRight: Radius.circular(16),
      ),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: const BoxDecoration(
          border: Border(
              top: BorderSide(color: AppColors.divider, width: 0.5)),
        ),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.add_rounded, color: AppColors.primary, size: 20),
            SizedBox(width: 8),
            Text(
              'Add Broker Account',
              style: TextStyle(
                color: AppColors.primary,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSettingsTile({
    required IconData icon,
    required String title,
    required String subtitle,
    Color? iconColor,
    Widget? trailing,
    VoidCallback? onTap,
  }) {
    return ListTile(
      onTap: onTap,
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: (iconColor ?? AppColors.textSecondary).withAlpha(20),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Center(
          child: Icon(icon, color: iconColor ?? AppColors.textSecondary, size: 20),
        ),
      ),
      title: Text(
        title,
        style: const TextStyle(
          color: AppColors.textPrimary,
          fontSize: 14,
          fontWeight: FontWeight.w500,
        ),
      ),
      subtitle: Text(
        subtitle,
        style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
      ),
      trailing: trailing ??
          const Icon(Icons.chevron_right_rounded,
              color: AppColors.textMuted, size: 20),
    );
  }

  Future<void> _showAddAccountDialog(BuildContext context) async {
    final nameCtrl = TextEditingController();
    final keyCtrl = TextEditingController();
    final secretCtrl = TextEditingController();

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.cardDark,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'Add Broker Account',
          style: TextStyle(color: AppColors.textPrimary),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _StyledTextField(
                  controller: nameCtrl, label: 'Account Name', hint: 'e.g. Zerodha-1'),
              const SizedBox(height: 12),
              _StyledTextField(controller: keyCtrl, label: 'API Key'),
              const SizedBox(height: 12),
              _StyledTextField(
                  controller: secretCtrl, label: 'API Secret', obscure: true),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel',
                style: TextStyle(color: AppColors.textMuted)),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.primary,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );

    if (result == true &&
        nameCtrl.text.isNotEmpty &&
        keyCtrl.text.isNotEmpty &&
        secretCtrl.text.isNotEmpty) {
      await SecureStorageService.saveApiKey(nameCtrl.text, keyCtrl.text);
      await SecureStorageService.saveApiSecret(nameCtrl.text, secretCtrl.text);
      await _loadAccounts();
    }

    nameCtrl.dispose();
    keyCtrl.dispose();
    secretCtrl.dispose();
  }

  Future<void> _confirmDeleteAccount(String accountName) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.cardDark,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text('Remove Account',
            style: TextStyle(color: AppColors.textPrimary)),
        content: Text(
          'Remove credentials for "$accountName"? This cannot be undone.',
          style: const TextStyle(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel',
                style: TextStyle(color: AppColors.textMuted)),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.loss),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await SecureStorageService.deleteAccount(accountName);
      await _loadAccounts();
    }
  }

  Future<void> _showClearDataDialog(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.cardDark,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text('Clear All Data',
            style: TextStyle(color: AppColors.loss)),
        content: const Text(
          'This will remove all stored API credentials and cached data. Are you sure?',
          style: TextStyle(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel',
                style: TextStyle(color: AppColors.textMuted)),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.loss),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Clear Everything'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await SecureStorageService.clearAll();
      await _loadAccounts();
    }
  }
}

class _StyledTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String? hint;
  final bool obscure;

  const _StyledTextField({
    required this.controller,
    required this.label,
    this.hint,
    this.obscure = false,
  });

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      style: const TextStyle(color: AppColors.textPrimary, fontSize: 14),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        labelStyle: const TextStyle(color: AppColors.textMuted, fontSize: 13),
        hintStyle: const TextStyle(color: AppColors.textMuted, fontSize: 13),
        filled: true,
        fillColor: AppColors.cardDarkElevated,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      ),
    );
  }
}
